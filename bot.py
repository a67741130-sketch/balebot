import os
import time
import uuid
import json
import sqlite3
import threading
import requests
from flask import Flask, request

app = Flask(__name__)

# ================= CONFIG =================
TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

ROUND_TIME = 300  # 5 minutes

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

# ================= MEMORY =================
timers = {}

# ================= SEND =================
def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(BASE_URL + "/sendMessage", data=data)

# ================= UI =================
def main_menu():
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
        g["round"], g["p1_move"], g["p2_move"], g["finished"], g["game_id"]
    ))
    conn.commit()

# ================= TIMER =================
def start_timer(game_id):
    def run():
        time.sleep(ROUND_TIME)

        g = get_game(game_id)
        if not g or g["finished"]:
            return

        if g["p1_move"] is None or g["p2_move"] is None:

            if g["p1_move"] is None:
                g["p2_score"] += 1
                send(g["p2"], "⏱ حریف انتخاب نکرد → امتیاز برای شما ثبت شد")
                send(g["p1"], "⏱ زمان تمام شد → امتیاز برای حریف")

            if g["p2_move"] is None:
                g["p1_score"] += 1
                send(g["p1"], "⏱ حریف انتخاب نکرد → امتیاز برای شما ثبت شد")
                send(g["p2"], "⏱ زمان تمام شد → امتیاز برای حریف")

            next_round(g)

    t = threading.Thread(target=run)
    t.start()
    timers[game_id] = t


# ================= ROUND CONTROL =================
def next_round(g):
    if g["finished"]:
        return

    # reset moves
    g["p1_move"] = None
    g["p2_move"] = None
    g["round"] += 1

    # tie break
    if g["round"] == 4:
        send(g["p1"], "🔥 راند نهایی شروع شد")
        send(g["p2"], "🔥 راند نهایی شروع شد")

    # finish
    if g["round"] > 4:
        end_game(g)
        return

    update(g)

    send(g["p1"], round_text(g["round"]), choices())
    send(g["p2"], round_text(g["round"]), choices())

    start_timer(g["game_id"])


def round_text(n):
    return f"""
راند {n}️⃣

🎮 از بین سه گزینه زیر انتخاب خود را انجام دهید

⚠️ توجه:
⏱ زمان انتخاب ۵ دقیقه است
❗ در صورت عدم انتخاب، امتیاز برای حریف ثبت می‌شود
"""

# ================= END GAME =================
def end_game(g):
    g["finished"] = 1
    update(g)

    p1 = g["p1_score"]
    p2 = g["p2_score"]

    result = f"📊 نتیجه: {p1} - {p2}"

    if p1 > p2:
        send(g["p1"], f"🎉 تبریک!\nشما برنده شدید 🏆\n\n{result}")
        send(g["p2"], f"😔 ای بابا\nباختی...\nبعدی جبران کن 💪\n\n{result}")
    else:
        send(g["p2"], f"🎉 تبریک!\nشما برنده شدید 🏆\n\n{result}")
        send(g["p1"], f"😔 ای بابا\nباختی...\nبعدی جبران کن 💪\n\n{result}")

# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    # ========== MESSAGE ==========
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send(chat_id, "🎮 ULTRA++ READY", main_menu())

    # ========== CALLBACK ==========
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        # CREATE
        if action == "create":
            gid = create_game(chat_id, "code")
            send(chat_id, f"کد بازی: {gid}")
            return "ok"

        # RANDOM
        if action == "random":
            send(chat_id, "⏳ در حال پیدا کردن حریف...")

        # GAME ACTION
        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()

        if not row:
            return "ok"

        g = get_game(row[0])

        role = "p1" if chat_id == g["p1"] else "p2"

        if role == "p1" and g["p1_move"]:
            return "ok"
        if role == "p2" and g["p2_move"]:
            return "ok"

        g[role + "_move"] = action
        send(chat_id, "✅ انتخاب ثبت شد")

        update(g)

        if g["p1_move"] and g["p2_move"]:
            r = win(g["p1_move"], g["p2_move"])

            if r == 1:
                g["p1_score"] += 1
            elif r == 2:
                g["p2_score"] += 1

            update(g)
            next_round(g)

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
