import os
import uuid
import json
import sqlite3
import threading
import requests
import random
from flask import Flask, request
from collections import deque

app = Flask(__name__)

lock = threading.Lock()

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ================= DB =================
conn = sqlite3.connect("game.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    p1 INTEGER,
    p2 TEXT,
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

# ================= SAFE SEND =================
def send(chat_id, text, reply_markup=None):
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        requests.post(BASE_URL + "/sendMessage", data=payload, timeout=5)
    except:
        pass


# ================= UI (UNCHANGED TEXT) =================
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


def round_text(n):
    return f"""
🎮 راند {n}️⃣

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
    cur.execute("""
    INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,0)
    """, (gid, p1, None, 0, 0, 1, None, None, mode))
    conn.commit()
    return gid


def get_game(user):
    cur.execute("SELECT * FROM games WHERE p1=? OR p2=?", (user, user))
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
    UPDATE games SET p2=?, p1_score=?, p2_score=?, round=?,
    p1_move=?, p2_move=?, finished=? WHERE game_id=?
    """, (
        g["p2"], g["p1_score"], g["p2_score"],
        g["round"], g["p1_move"], g["p2_move"],
        g["finished"], g["game_id"]
    ))
    conn.commit()


# ================= NEXT ROUND (SAFE) =================
def next_round(g):
    if g["finished"]:
        return

    g["p1_move"] = None
    g["p2_move"] = None
    g["round"] += 1

    update(g)

    if g["round"] <= 3 or (g["round"] == 4 and g["p1_score"] == g["p2_score"]):
        send(g["p1"], round_text(g["round"]), choices())

        if g["p2"] == "BOT":
            g["p2_move"] = random.choice(["rock", "paper", "scissors"])
            process(g)
        else:
            send(g["p2"], round_text(g["round"]), choices())
        return

    end_game(g)


# ================= PROCESS =================
def process(g):
    r = win(g["p1_move"], g["p2_move"])

    if r == 1:
        g["p1_score"] += 1
        send(g["p1"], "🏆 شما یه امتیاز گرفتید")
        send(g["p2"], "😔 حریف یه امتیاز گرفت")
    elif r == 2:
        g["p2_score"] += 1
        send(g["p2"], "🏆 شما یه امتیاز گرفتید")
        send(g["p1"], "😔 حریف یه امتیاز گرفت")
    else:
        send(g["p1"], "🤝 مساوی")
        send(g["p2"], "🤝 مساوی")

    update(g)
    next_round(g)


# ================= END GAME =================
def end_game(g):
    g["finished"] = 1
    update(g)

    result = f"📊 نتیجه: {g['p1_score']} - {g['p2_score']}"

    if g["p1_score"] > g["p2_score"]:
        send(g["p1"], f"🎉 تبریک\nشما برنده شدید 🏆\n{result}")
        send(g["p2"], f"😔 ای بابا\nباختی\n{result}")
    else:
        send(g["p2"], f"🎉 تبریک\nشما برنده شدید 🏆\n{result}")
        send(g["p1"], f"😔 ای بابا\nباختی\n{result}")


# ================= BOT =================
def start_bot(user):
    gid = create_game(user, "bot")
    g = get_game(user)
    g["p2"] = "BOT"
    update(g)

    send(user, "🤖 بازی با ربات شروع شد")
    send(user, round_text(1), choices())


# ================= RANDOM =================
def match_random(user):
    if queue and queue[0] != user:
        opp = queue.popleft()

        gid = create_game(opp, "random")
        g = get_game(opp)
        g["p2"] = user
        update(g)

        send(opp, "🎮 حریف پیدا شد")
        send(user, "🎮 حریف پیدا شد")

        send(opp, round_text(1), choices())
        send(user, round_text(1), choices())
    else:
        if user not in queue:
            queue.append(user)
        send(user, "⏳ در حال پیدا کردن حریف...")


# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send(chat_id,
                 "سلام👋\nبه بازی سنگ کاغذ قیچی خوش اومدی🎮\nبرای شروع مود بازیتو انتخاب کن👇",
                 menu())

    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        if action == "bot":
            start_bot(chat_id)
            return "ok"

        if action == "random":
            match_random(chat_id)
            return "ok"

        if action == "create":
            gid = create_game(chat_id, "code")
            send(chat_id, f"🔑 کد: {gid}")
            return "ok"

        if action == "join":
            send(chat_id, "کد رو بفرست")
            return "ok"

        g = get_game(chat_id)
        if not g:
            return "ok"

        role = "p1" if chat_id == g["p1"] else "p2"

        with lock:
            g[role + "_move"] = action
            send(chat_id, "✅ انتخاب ثبت شد")

            update(g)

            if g["p1_move"] and g["p2_move"]:
                process(g)

        return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
