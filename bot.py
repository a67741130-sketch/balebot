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
TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
ROUND_TIME = 300

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

queue = deque()
active_games = {}

# ================= SAFE SEND =================
def send(chat_id, text, reply_markup=None):
    try:
        data = {"chat_id": chat_id, "text": text}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        requests.post(
            BASE_URL + "/sendMessage",
            data=data,
            timeout=5
        )
    except Exception as e:
        print("SEND ERROR:", e)

# ================= UI =================
def menu():
    return {
        "inline_keyboard": [
            [{"text": "🆕 ساخت بازی", "callback_data": "create"}],
            [{"text": "🔑 ورود با کد", "callback_data": "join"}],
            [{"text": "🎲 بازی رندوم", "callback_data": "random"}]
        ]
    }


def choices():
    return {
        "inline_keyboard": [[
            {"text": "✊", "callback_data": "rock"},
            {"text": "✋", "callback_data": "paper"},
            {"text": "✌️", "callback_data": "scissors"}
        ]]
    }

# ================= GAME CORE (بدون تغییر) =================
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

    cur.execute("""
    INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,0)
    """, (gid, p1, None, 0, 0, 1, None, None, mode))

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

# ================= TIMER (بدون دستکاری منطق) =================
def start_timer(game_id):
    def run():
        time.sleep(ROUND_TIME)

        g = get_game(game_id)
        if not g or g["finished"]:
            return

        with game_lock:
            if g["p1_move"] is None or g["p2_move"] is None:

                if g["p1_move"] is None:
                    g["p2_score"] += 1
                    send(g["p2"], "⏱ حریف انتخاب نکرد → شما امتیاز گرفتید")
                    send(g["p1"], "⏱ زمان تمام شد → امتیاز برای حریف")

                if g["p2_move"] is None:
                    g["p1_score"] += 1
                    send(g["p1"], "⏱ حریف انتخاب نکرد → شما امتیاز گرفتید")
                    send(g["p2"], "⏱ زمان تمام شد → امتیاز برای حریف")

                update(g)
                next_round(g)

    threading.Thread(target=run, daemon=True).start()

# ================= ROUND =================
def round_text(n):
    return f"""
🎮 راند {n}️⃣

از بین گزینه‌های زیر انتخاب کنید:

⚠️ توجه:
⏱ زمان انتخاب: ۵ دقیقه
❗ در صورت عدم انتخاب، امتیاز برای حریف ثبت می‌شود
"""

# ================= NEXT ROUND (بدون تغییر) =================
def next_round(g):
    if g["finished"]:
        return

    g["p1_move"] = None
    g["p2_move"] = None
    g["round"] += 1

    update(g)

    if g["round"] <= 3:
        send(g["p1"], round_text(g["round"]), choices())
        send(g["p2"], round_text(g["round"]), choices())
        start_timer(g["game_id"])
        return

    p1 = g["p1_score"]
    p2 = g["p2_score"]

    if p1 != p2:
        end_game(g)
        return

    send(g["p1"], "🔥 نتیجه مساوی است! راند نهایی شروع شد")
    send(g["p2"], "🔥 نتیجه مساوی است! راند نهایی شروع شد")

    g["round"] += 1
    update(g)

    send(g["p1"], round_text(g["round"]), choices())
    send(g["p2"], round_text(g["round"]), choices())

    start_timer(g["game_id"])

# ================= END GAME =================
def end_game(g):
    g["finished"] = 1
    update(g)

    p1 = g["p1_score"]
    p2 = g["p2_score"]

    result = f"📊 نتیجه نهایی: {p1} - {p2}"

    if p1 > p2:
        send(g["p1"], f"🎉 تبریک!\nشما برنده شدید 🏆\n\n{result}")
        send(g["p2"], f"😔 ای بابا\nباختی...\nجبران می‌کنی 💪\n\n{result}")
    else:
        send(g["p2"], f"🎉 تبریک!\nشما برنده شدید 🏆\n\n{result}")
        send(g["p1"], f"😔 ای بابا\nباختی...\nجبران می‌کنی 💪\n\n{result}")

# ================= WEBHOOK PRO FIX =================
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return "OK"

    try:
        data = request.get_json(silent=True)
        if not data:
            return "ok"

        print("🔥 UPDATE:", data)

        # MESSAGE
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")

            if text == "/start":
                send(chat_id, "سلام👋\nبه بازی سنگ کاغذ قیچی خوش اومدی🎮\nبرای شروع مود بازیتو انتخاب کن👇", menu())

        # CALLBACK
        if "callback_query" in data:
            cq = data["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            action = cq["data"]

            if action == "create":
                gid = create_game(chat_id, "code")
                send(chat_id, f"🔑 کد بازی شما:\n{gid}")
                return "ok"

            if action == "join":
                send(chat_id, "📩 کد بازی را ارسال کنید")
                return "ok"

            if action == "random":
                send(chat_id, "🎲 سیستم رندوم فعال")
                return "ok"

        return "ok"

    except Exception as e:
        print("WEBHOOK ERROR:", e)
        return "ok"

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
