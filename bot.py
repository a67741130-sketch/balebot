from flask import Flask, request
import requests
import sqlite3
import uuid
import json
import os
from collections import deque

app = Flask(__name__)

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ================= DB =================
conn = sqlite3.connect("ultra.db", check_same_thread=False)
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
    mode TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0
)
""")

conn.commit()

# ================= QUEUE =================
queue = deque()

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
    cur.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?)",
                (gid, p1, None, 0, 0, 1, None, None, mode))
    conn.commit()
    return gid


def get_game(gid):
    cur.execute("SELECT * FROM games WHERE game_id=?", (gid,))
    r = cur.fetchone()
    if not r:
        return None
    return {
        "game_id": r[0],
        "p1": r[1],
        "p2": r[2],
        "p1_score": r[3],
        "p2_score": r[4],
        "round": r[5],
        "p1_move": r[6],
        "p2_move": r[7],
        "mode": r[8]
    }


def update(g):
    cur.execute("""
    UPDATE games SET p2=?, p1_score=?, p2_score=?, round=?, p1_move=?, p2_move=?, mode=?
    WHERE game_id=?
    """, (
        g["p2"], g["p1_score"], g["p2_score"],
        g["round"], g["p1_move"], g["p2_move"], g["mode"], g["game_id"]
    ))
    conn.commit()


def update_user(uid, win_flag):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    u = cur.fetchone()

    if not u:
        cur.execute("INSERT INTO users VALUES (?,?,?)", (uid, 0, 0))

    if win_flag == 1:
        cur.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (uid,))
    elif win_flag == 2:
        cur.execute("UPDATE users SET losses = losses + 1 WHERE user_id=?", (uid,))

    conn.commit()


# ================= MATCHMAKING ULTRA =================
def match(user):
    if queue and queue[0] != user:
        opponent = queue.popleft()

        gid = create_game(opponent, "random")
        g = get_game(gid)
        g["p2"] = user
        update(g)

        send(opponent, "🎮 حریف پیدا شد!")
        send(user, "🎮 حریف پیدا شد!")

        send(opponent, "راند 1", choices())
        send(user, "راند 1", choices())
    else:
        if user not in queue:
            queue.append(user)
        send(user, "⏳ در حال پیدا کردن حریف...")


# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    # -------- MESSAGE --------
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = (data["message"].get("text") or "").strip()

        if text == "/start":
            send(chat_id, "🚀 ULTRA VERSION ACTIVE", menu())

    # -------- CALLBACK --------
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        # CREATE
        if action == "create":
            gid = create_game(chat_id, "code")
            send(chat_id, gid)
            return "ok"

        # JOIN
        if action == "join":
            send(chat_id, "📩 کد را ارسال کنید")
            return "ok"

        # RANDOM
        if action == "random":
            match(chat_id)
            return "ok"

        # GET GAME
        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()
        if not row:
            return "ok"

        g = get_game(row[0])

        role = "p1" if chat_id == g["p1"] else "p2"

        # ANTI DOUBLE MOVE
        if role == "p1" and g["p1_move"]:
            return "ok"
        if role == "p2" and g["p2_move"]:
            return "ok"

        if role == "p1":
            g["p1_move"] = action
        else:
            g["p2_move"] = action

        update(g)

        send(chat_id, "✅ انتخاب شما ثبت شد")

        # ROUND END
        if g["p1_move"] and g["p2_move"]:
            r = win(g["p1_move"], g["p2_move"])

            if r == 1:
                g["p1_score"] += 1
                send(g["p1"], "🏆 شما یک امتیاز گرفتید")
                send(g["p2"], "📉 حریف شما یک امتیاز گرفت")
                update_user(g["p1"], 1)
                update_user(g["p2"], 2)

            elif r == 2:
                g["p2_score"] += 1
                send(g["p2"], "🏆 شما یک امتیاز گرفتید")
                send(g["p1"], "📉 حریف شما یک امتیاز گرفت")
                update_user(g["p2"], 1)
                update_user(g["p1"], 2)

            else:
                send(g["p1"], "🤝 مساوی")
                send(g["p2"], "🤝 مساوی")

            g["p1_move"] = None
            g["p2_move"] = None
            g["round"] += 1

            if g["round"] > 3:
                final = f"🏁 پایان بازی\n{g['p1_score']} - {g['p2_score']}"
                send(g["p1"], final)
                send(g["p2"], final)
                return "ok"

            update(g)

            send(g["p1"], f"راند {g['round']}", choices())
            send(g["p2"], f"راند {g['round']}", choices())

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
