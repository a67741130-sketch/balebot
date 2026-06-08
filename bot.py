from flask import Flask, request
import requests
import uuid
import json
import os
import sqlite3

app = Flask(__name__)

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ================= DB =================
conn = sqlite3.connect("uber.db", check_same_thread=False)
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
conn.commit()


# ================= MATCHMAKING QUEUE =================
queue = []  # users waiting for random match


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
            [{"text": "🆔 بازی با کد", "callback_data": "code"}],
            [{"text": "🎲 بازی رندوم", "callback_data": "random"}]
        ]
    }


def copy_code(code):
    # واقعی‌ترین حالت: متن آماده کپی
    return {
        "inline_keyboard": [[
            {"text": f"📋 کد: {code} (لمس برای کپی)", "callback_data": f"copy:{code}"}
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


# ================= GAME =================
def win(a, b):
    if a == b:
        return 0
    if (a == "rock" and b == "scissors") or \
       (a == "paper" and b == "rock") or \
       (a == "scissors" and b == "paper"):
        return 1
    return 2


def create_game(game_id, p1, mode):
    cur.execute("""
    INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (game_id, p1, None, 0, 0, 1, None, None, mode))
    conn.commit()


def get_game(game_id):
    cur.execute("SELECT * FROM games WHERE game_id=?", (game_id,))
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
        g["p2"],
        g["p1_score"],
        g["p2_score"],
        g["round"],
        g["p1_move"],
        g["p2_move"],
        g["mode"],
        g["game_id"]
    ))
    conn.commit()


# ================= MATCHMAKING =================
def try_match(user):
    if queue:
        opponent = queue.pop(0)

        game_id = str(uuid.uuid4())[:6]
        create_game(game_id, opponent, "random")

        game = get_game(game_id)
        game["p2"] = user
        update(game)

        send(opponent, "🎮 حریف پیدا شد!")
        send(user, "🎮 حریف پیدا شد!")

        send(opponent, "شروع بازی", choices())
        send(user, "شروع بازی", choices())

    else:
        queue.append(user)
        send(user, "⏳ در حال پیدا کردن حریف...")


# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    # ---------------- MESSAGE ----------------
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = (data["message"].get("text") or "").strip()

        if text == "/start":
            send(chat_id, "🎮 Uber RPS", main_menu())

    # ---------------- CALLBACK ----------------
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        # MENU
        if action == "code":
            game_id = str(uuid.uuid4())[:6]
            create_game(game_id, chat_id, "code")

            send(chat_id,
                 f"🎯 کد بازی:\n{game_id}",
                 copy_code(game_id)
            )
            return "ok"

        if action == "random":
            try_match(chat_id)
            return "ok"

        # COPY (FIXED - REAL)
        if action.startswith("copy:"):
            code = action.split(":")[1]
            send(chat_id, f"📋 کپی کن:\n{code}")
            return "ok"

        # GAME LOGIC
        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()
        if not row:
            return "ok"

        g = get_game(row[0])

        player = "p1" if chat_id == g["p1"] else "p2"

        if player == "p1":
            if g["p1_move"]:
                return "ok"
            g["p1_move"] = action
        else:
            if g["p2_move"]:
                return "ok"
            g["p2_move"] = action

        update(g)

        if g["p1_move"] and g["p2_move"]:
            r = win(g["p1_move"], g["p2_move"])

            if r == 1:
                g["p1_score"] += 1
                send(g["p1"], "🏆 شما یک امتیاز گرفتید")
                send(g["p2"], "😢 حریف شما یک امتیاز گرفت")
            elif r == 2:
                g["p2_score"] += 1
                send(g["p2"], "🏆 شما یک امتیاز گرفتید")
                send(g["p1"], "😢 حریف شما یک امتیاز گرفت")
            else:
                send(g["p1"], "🤝 مساوی")
                send(g["p2"], "🤝 مساوی")

            g["p1_move"] = None
            g["p2_move"] = None
            g["round"] += 1

            # 3 ROUND LIMIT
            if g["round"] > 3:
                result = f"🎮 پایان\nشما: {g['p1_score']} | حریف: {g['p2_score']}"
                send(g["p1"], result)
                send(g["p2"], result)
                return "ok"

            update(g)

            send(g["p1"], f"راند {g['round']}", choices())
            send(g["p2"], f"راند {g['round']}", choices())

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
