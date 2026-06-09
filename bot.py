import os
import time
import uuid
import json
import sqlite3
import threading
import requests
from flask import Flask, request
from collections import deque

app = Flask(__name__)

game_lock = threading.Lock()

# ================= CONFIG =================
TOKEN = "YOUR_TOKEN"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
ROUND_TIME = 300
MAX_ROUNDS = 3

# ================= DB =================
conn = sqlite3.connect("game.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    p1 INTEGER,
    p2 INTEGER,
    p1_score INTEGER,
    p2_score INTEGER,
    round INTEGER,
    p1_move TEXT,
    p2_move TEXT,
    mode TEXT,
    finished INTEGER DEFAULT 0
)
""")
conn.commit()

# ================= STATE =================
queue = deque()
active_games = {}

# ================= SEND =================
def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(BASE_URL + "/sendMessage", data=data)

# ================= UI =================
def menu():
    return {
        "inline_keyboard": [
            [{"text": "🆕 ساخت بازی", "callback_data": "create"}],
            [{"text": "🔑 ورود با کد", "callback_data": "join"}],
            [{"text": "🎲 بازی رندوم", "callback_data": "random"}]
        ]
    }

def share_keyboard(code):
    return {
        "inline_keyboard": [[
            {
                "text": "📤 اشتراک گذاری",
                "url": f"https://t.me/share/url?text=Join%20my%20game%20code:%20{code}"
            }
        ]]
    }

def choices():
    return {
        "inline_keyboard": [[
            {"text": "✊", "callback_data": "rock"},
            {"text": "✋", "callback_data": "paper"},
            {"text": "✌️", "callback_data": "scissors"}
        ]]
    }

def round_text(n):
    return f"""🎮 راند {n}️⃣

از بین گزینه‌های زیر انتخاب کنید:

⚠️ توجه:
⏱ زمان انتخاب: ۵ دقیقه
❗ در صورت عدم انتخاب، امتیاز برای حریف ثبت می‌شود
"""

# ================= GAME CORE =================
def win(a, b):
    if a == b:
        return 0
    if (a == "rock" and b == "scissors") or \
       (a == "paper" and b == "rock") or \
       (a == "scissors" and b == "paper"):
        return 1
    return 2


def create_game(p1, mode):
    gid = str(uuid.uuid4())[:6]
    cur.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,0)",
                (gid, p1, None, 0, 0, 1, None, None, mode))
    conn.commit()
    return gid


def get_game(gid):
    cur.execute("SELECT * FROM games WHERE game_id=?", (gid,))
    g = cur.fetchone()
    if not g:
        return None

    return {
        "game_id": g[0],
        "p1": g[1],
        "p2": g[2],
        "p1_score": g[3],
        "p2_score": g[4],
        "round": g[5],
        "p1_move": g[6],
        "p2_move": g[7],
        "mode": g[8],
        "finished": g[9]
    }


def update(g):
    cur.execute("""
    UPDATE games SET p2=?, p1_score=?, p2_score=?, round=?, p1_move=?, p2_move=?, finished=?
    WHERE game_id=?
    """, (
        g["p2"], g["p1_score"], g["p2_score"],
        g["round"], g["p1_move"], g["p2_move"],
        g["finished"], g["game_id"]
    ))
    conn.commit()

# ================= GAME FLOW =================
def end_game(g):
    g["finished"] = 1
    update(g)

    p1, p2 = g["p1_score"], g["p2_score"]

    result = f"📊 نتیجه نهایی: {p1} - {p2}"

    if p1 > p2:
        send(g["p1"], f"🎉 تبریک\nشما برنده شدید 🏆\n\n{result}")
        send(g["p2"], f"😔 ای بابا\nای بازی رو باختی\nولی جبران میکنی 💪\n\n{result}")
    else:
        send(g["p2"], f"🎉 تبریک\nشما برنده شدید 🏆\n\n{result}")
        send(g["p1"], f"😔 ای بابا\nای بازی رو باختی\nولی جبران میکنی 💪\n\n{result}")


def next_round(g):
    if g["finished"]:
        return

    g["p1_move"] = None
    g["p2_move"] = None
    g["round"] += 1
    update(g)

    # ===== NORMAL ROUNDS =====
    if g["round"] <= MAX_ROUNDS:

        send(g["p1"], round_text(g["round"]), choices())
        send(g["p2"], round_text(g["round"]), choices())

        start_timer(g["game_id"])
        return

    # ===== FINAL ROUND LOGIC =====
    if g["p1_score"] != g["p2_score"]:
        end_game(g)
        return

    send(g["p1"], "🔥 نتیجه مساوی شد، راند نهایی شروع شد")
    send(g["p2"], "🔥 نتیجه مساوی شد، راند نهایی شروع شد")

    g["round"] += 1
    update(g)

    send(g["p1"], round_text(g["round"]), choices())
    send(g["p2"], round_text(g["round"]), choices())

    start_timer(g["game_id"])


def start_timer(game_id):
    def run():
        time.sleep(ROUND_TIME)

        with game_lock:
            g = get_game(game_id)
            if not g or g["finished"]:
                return

            if g["p1_move"] is None:
                g["p2_score"] += 1
                send(g["p2"], "⏱ حریف انتخاب نکرد → شما امتیاز گرفتید")
                send(g["p1"], "⏱ شما انتخاب نکردید → حریف امتیاز گرفت")

            if g["p2_move"] is None:
                g["p1_score"] += 1
                send(g["p1"], "⏱ حریف انتخاب نکرد → شما امتیاز گرفتید")
                send(g["p2"], "⏱ شما انتخاب نکردید → حریف امتیاز گرفت")

            update(g)
            next_round(g)

    threading.Thread(target=run, daemon=True).start()

# ================= MATCHMAKING =================
def match_random(user_id):
    if queue and queue[0] != user_id:
        opponent = queue.popleft()

        gid = create_game(opponent, "random")
        g = get_game(gid)
        g["p2"] = user_id
        update(g)

        send(opponent, "🎮 حریف پیدا شد!")
        send(user_id, "🎮 حریف پیدا شد!")

        send(opponent, round_text(1), choices())
        send(user_id, round_text(1), choices())

        start_timer(gid)
    else:
        if user_id not in queue:
            queue.append(user_id)
        send(user_id, "⏳ در حال پیدا کردن حریف...")

# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    try:
        data = request.get_json(silent=True)

        if not data:
            return "ok"

        # ================= MESSAGE =================
        msg = data.get("message")
        if msg:
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")

            if text == "/start":
                send(
                    chat_id,
                    "سلام 👋\nبه بازی سنگ کاغذ قیچی خوش اومدی 🎮\nمود بازی رو انتخاب کن 👇",
                    menu()
                )

            return "ok"

        # ================= CALLBACK =================
        cq = data.get("callback_query")
        if cq:
            chat_id = cq["message"]["chat"]["id"]
            action = cq.get("data")

            # ===== CREATE =====
            if action == "create":
                gid = create_game(chat_id, "code")
                send(chat_id, f"🔑 کد بازی شما:\n{gid}")
                return "ok"

            # ===== JOIN =====
            if action == "join":
                send(chat_id, "📩 کد بازی را ارسال کنید")
                return "ok"

            # ===== RANDOM =====
            if action == "random":
                match_random(chat_id)
                return "ok"

            # ===== FIND GAME =====
            cur.execute(
                "SELECT game_id FROM games WHERE p1=? OR p2=?",
                (chat_id, chat_id)
            )
            row = cur.fetchone()

            if not row:
                return "ok"

            g = get_game(row[0])
            if not g:
                return "ok"

            role = "p1" if chat_id == g["p1"] else "p2"

            # anti double click
            if role == "p1" and g["p1_move"]:
                return "ok"
            if role == "p2" and g["p2_move"]:
                return "ok"

            with game_lock:
                g[role + "_move"] = action
                send(chat_id, "✅ انتخاب شما ثبت شد")

                update(g)

                # ===== ROUND COMPLETE =====
                if g["p1_move"] and g["p2_move"]:
                    r = win(g["p1_move"], g["p2_move"])

                    if r == 1:
                        g["p1_score"] += 1
                        send(g["p1"], "🏆 شما یک امتیاز گرفتید")
                        send(g["p2"], "😔 حریف یک امتیاز گرفت")

                    elif r == 2:
                        g["p2_score"] += 1
                        send(g["p2"], "🏆 شما یک امتیاز گرفتید")
                        send(g["p1"], "😔 حریف یک امتیاز گرفت")

                    else:
                        send(g["p1"], "🤝 این راند مساوی شد")
                        send(g["p2"], "🤝 این راند مساوی شد")

                    update(g)
                    next_round(g)

            return "ok"

        return "ok"

    except Exception as e:
        print("WEBHOOK CRASH FIXED:", e)
        return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
