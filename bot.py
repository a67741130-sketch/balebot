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
            [{"text": "🤖 بازی با ربات", "callback_data": "bot"}],
            [{"text": "🎲 بازی رندوم", "callback_data": "random"}]
        ]
    }


def share_keyboard(game_id):
    return {
        "inline_keyboard": [
            [{"text": "📤 اشتراک‌گذاری کد", "switch_inline_query": game_id}]
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


# ================= BOT GAME =================
def bot_game(user_id):
    gid = create_game(user_id, "bot")
    g = get_game(gid)
    g["p2"] = -1  # bot
    update(g)

    active_games[gid] = g

    send(user_id, "🤖 بازی با ربات شروع شد!")
    send(user_id, round_text(1), choices())

    start_timer(gid)
    return gid


def bot_move():
    return ["rock", "paper", "scissors"][int(time.time()) % 3]


# ================= TIMER =================
def start_timer(game_id):
    def run():
        time.sleep(ROUND_TIME)

        g = get_game(game_id)
        if not g or g["finished"]:
            return

        with game_lock:

            # BOT MODE
            if g["mode"] == "bot" and g["p2"] == -1:
                if g["p1_move"] is None:
                    g["p1_move"] = bot_move()

            # TIME OUT HANDLING
            if g["p1_move"] is None:
                g["p2_score"] += 1
            if g["p2_move"] is None:
                g["p1_score"] += 1

            update(g)
            next_round(g)

    threading.Thread(target=run, daemon=True).start()


# ================= ROUND =================
def round_text(n):
    return f"🎮 راند {n}\nانتخاب کن 👇"


def next_round(g):
    if g["finished"]:
        return

    g["p1_move"] = None
    g["p2_move"] = None
    g["round"] += 1

    update(g)

    if g["round"] <= 3:
        send(g["p1"], round_text(g["round"]), choices())
        if g["p2"] != -1:
            send(g["p2"], round_text(g["round"]), choices())
        start_timer(g["game_id"])
        return

    if g["p1_score"] != g["p2_score"]:
        return end_game(g)

    send(g["p1"], "🔥 راند نهایی!")
    if g["p2"] != -1:
        send(g["p2"], "🔥 راند نهایی!")

    g["round"] += 1
    update(g)

    send(g["p1"], round_text(g["round"]), choices())
    if g["p2"] != -1:
        send(g["p2"], round_text(g["round"]), choices())

    start_timer(g["game_id"])


def end_game(g):
    g["finished"] = 1
    update(g)

    p1, p2 = g["p1_score"], g["p2_score"]

    if p2 == -1:
        send(g["p1"], f"📊 نتیجه: {p1}")
        return

    if p1 > p2:
        send(g["p1"], "🏆 بردی")
        send(g["p2"], "😔 باختی")
    else:
        send(g["p2"], "🏆 بردی")
        send(g["p1"], "😔 باختی")


# ================= RANDOM MATCH =================
def match_random(user_id):
    if queue and queue[0] != user_id:
        opponent = queue.popleft()

        gid = create_game(opponent, "random")
        g = get_game(gid)
        g["p2"] = user_id
        update(g)

        send(opponent, "🎮 حریف پیدا شد")
        send(user_id, "🎮 حریف پیدا شد")

        send(opponent, round_text(1), choices())
        send(user_id, round_text(1), choices())

        start_timer(gid)
    else:
        if user_id not in queue:
            queue.append(user_id)
        send(user_id, "⏳ درحال جستجوی حریف...")


# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send(chat_id,
                 "سلام 👋\nبه بازی سنگ کاغذ قیچی خوش اومدی",
                 menu())

    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        if action == "bot":
            bot_game(chat_id)
            return "ok"

        if action == "create":
            gid = create_game(chat_id, "code")
            send(chat_id, f"🔑 کد: {gid}", share_keyboard(gid))
            return "ok"

        if action == "join":
            send(chat_id, "کد بازی را ارسال کن")
            return "ok"

        if action == "random":
            match_random(chat_id)
            return "ok"

        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()
        if not row:
            return "ok"

        g = get_game(row[0])
        role = "p1" if chat_id == g["p1"] else "p2"

        with game_lock:
            g[role + "_move"] = action
            send(chat_id, "ثبت شد")
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
