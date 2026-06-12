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

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
ROUND_TIME = 300

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
waiting_join = {}
active_games = {}

def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(BASE_URL + "/sendMessage", data=data)


def menu():
    return {
        "inline_keyboard": [
            [{"text": "🆕 ساخت بازی", "callback_data": "create"}],
            [{"text": "🔑 ورود با کد", "callback_data": "join"}],
            [{"text": "🎲 بازی رندوم", "callback_data": "random"}],
            [{"text": "🤖 بازی با ربات", "callback_data": "bot"}]
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


def bot_move():
    import random
    return random.choice(["rock", "paper", "scissors"])


# ================= MATCH RANDOM FIX =================
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


# ================= JOIN FIX =================
def join_game(user_id, gid):
    g = get_game(gid)
    if not g:
        send(user_id, "❌ بازی پیدا نشد")
        return

    if g["p2"] is None:
        g["p2"] = user_id
        update(g)

        send(g["p1"], "🎮 حریف وارد شد!")
        send(user_id, "🎮 وارد بازی شدی!")

        send(g["p1"], round_text(1), choices())
        send(user_id, round_text(1), choices())

        start_timer(gid)
    else:
        send(user_id, "❌ این بازی پر است")


# ================= TIMER FIX =================
def start_timer(game_id):
    def run():
        time.sleep(ROUND_TIME)

        g = get_game(game_id)
        if not g or g["finished"]:
            return

        with game_lock:
            if g["p1_move"] is None:
                g["p1_move"] = "rock"
            if g["p2_move"] is None and g["p2"] is not None:
                g["p2_move"] = "rock"
            if g["mode"] == "bot" and g["p2"] is None:
                g["p2_move"] = bot_move()

            update(g)
            process_round(g)

    threading.Thread(target=run, daemon=True).start()


def process_round(g):
    r = win(g["p1_move"], g["p2_move"] if g["p2_move"] else "rock")

    if r == 1:
        g["p1_score"] += 1
        send(g["p1"], "🏆 شما یک امتیاز گرفتید")
        if g["p2"]:
            send(g["p2"], "😔 حریف یک امتیاز گرفت")

    elif r == 2:
        g["p2_score"] += 1
        send(g["p2"], "🏆 شما یک امتیاز گرفتید")
        send(g["p1"], "😔 حریف یک امتیاز گرفت")
    else:
        send(g["p1"], "🤝 این راند مساوی شد")
        if g["p2"]:
            send(g["p2"], "🤝 این راند مساوی شد")

    update(g)
    next_round(g)


def round_text(n):
    return f"""
🎮 راند {n}️⃣

از بین گزینه‌های زیر انتخاب کنید:

⚠️ توجه:
⏱ زمان انتخاب: ۵ دقیقه
❗ در صورت عدم انتخاب، امتیاز برای حریف ثبت می‌شود
"""


def next_round(g):
    if g["finished"]:
        return

    g["p1_move"] = None
    g["p2_move"] = None
    g["round"] += 1

    update(g)

    if g["round"] > 3:
        end_game(g)
        return

    send(g["p1"], round_text(g["round"]), choices())
    if g["p2"]:
        send(g["p2"], round_text(g["round"]), choices())

    start_timer(g["game_id"])


def end_game(g):
    g["finished"] = 1
    update(g)

    result = f"📊 نتیجه: {g['p1_score']} - {g['p2_score']}"

    if g["p1_score"] > g["p2_score"]:
        send(g["p1"], f"🎉 تبریک!\nشما برنده شدید 🏆\n\n{result}")
        if g["p2"]:
            send(g["p2"], f"😔 ای بابا\nباختی...\nجبران می‌کنی 💪\n\n{result}")
    else:
        send(g["p2"], f"🎉 تبریک!\nشما برنده شدید 🏆\n\n{result}")
        send(g["p1"], f"😔 ای بابا\nباختی...\nجبران می‌کنی 💪\n\n{result}")


# ================= BOT MODE =================
def play_bot(user_id):
    gid = create_game(user_id, "bot")
    g = get_game(gid)
    g["p2"] = None
    update(g)

    send(user_id, "🤖 بازی با ربات شروع شد")
    send(user_id, round_text(1), choices())

    start_timer(gid)


# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send(chat_id,
                 "سلام👋\nبه بازی سنگ کاغذ قیچی خوش اومدی🎮\nبرای شروع مود بازیتو انتخاب کن👇",
                 menu())

        if chat_id in waiting_join:
            gid = text.strip()
            join_game(chat_id, gid)
            waiting_join.pop(chat_id, None)

    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        if action == "create":
            gid = create_game(chat_id, "code")
            send(chat_id, f"🔑 کد بازی شما:\n{gid}")
            return "ok"

        if action == "join":
            waiting_join[chat_id] = True
            send(chat_id, "📩 کد بازی را ارسال کنید")
            return "ok"

        if action == "random":
            match_random(chat_id)
            return "ok"

        if action == "bot":
            play_bot(chat_id)
            return "ok"

        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()
        if not row:
            return "ok"

        g = get_game(row[0])

        role = "p1" if chat_id == g["p1"] else "p2"

        if action in ["rock", "paper", "scissors"]:
            with game_lock:
                g[role + "_move"] = action
                send(chat_id, "✅ انتخاب شما ثبت شد")

                update(g)

                if g["p1_move"] and (g["p2_move"] or g["mode"] == "bot"):
                    if g["mode"] == "bot":
                        g["p2_move"] = bot_move()
                    process_round(g)

        return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
