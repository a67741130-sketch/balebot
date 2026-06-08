from flask import Flask, request
import requests
import uuid
import json
import os
import sqlite3

app = Flask(__name__)

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ================= DATABASE =================
conn = sqlite3.connect("games.db", check_same_thread=False)
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
    p2_move TEXT
)
""")
conn.commit()


# ================= SEND =================
def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    requests.post(BASE_URL + "/sendMessage", data=data)


# ================= BUTTONS =================
def choice_buttons():
    return {
        "inline_keyboard": [[
            {"text": "✊ سنگ", "callback_data": "rock"},
            {"text": "✋ کاغذ", "callback_data": "paper"},
            {"text": "✌️ قیچی", "callback_data": "scissors"}
        ]]
    }


def copy_button(code):
    return {
        "inline_keyboard": [[
            {
                "text": "📋 کپی کد بازی",
                "switch_inline_query": code
            }
        ]]
    }


# ================= GAME LOGIC =================
def winner(m1, m2):
    if m1 == m2:
        return 0
    if (m1 == "rock" and m2 == "scissors") or \
       (m1 == "paper" and m2 == "rock") or \
       (m1 == "scissors" and m2 == "paper"):
        return 1
    return 2


# ================= HELPERS =================
def create_game(game_id, p1):
    cur.execute("""
    INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (game_id, p1, None, 0, 0, 1, None, None))
    conn.commit()


def get_game(game_id):
    cur.execute("SELECT * FROM games WHERE game_id=?", (game_id,))
    row = cur.fetchone()
    if not row:
        return None

    return {
        "game_id": row[0],
        "p1": row[1],
        "p2": row[2],
        "p1_score": row[3],
        "p2_score": row[4],
        "round": row[5],
        "p1_move": row[6],
        "p2_move": row[7],
    }


def update_game(g):
    cur.execute("""
    UPDATE games
    SET p2=?, p1_score=?, p2_score=?, round=?, p1_move=?, p2_move=?
    WHERE game_id=?
    """, (
        g["p2"],
        g["p1_score"],
        g["p2_score"],
        g["round"],
        g["p1_move"],
        g["p2_move"],
        g["game_id"]
    ))
    conn.commit()


# ================= WEBHOOK =================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json(force=True)

    # ---------------- MESSAGE ----------------
    if "message" in data:
        msg = data["message"]
        text = (msg.get("text") or "").strip()
        chat_id = msg["chat"]["id"]

        # START
        if text.startswith("/start"):
            send(chat_id, "🎮 آماده‌ای؟\n/create برای ساخت بازی")

        # CREATE
        elif text.startswith("/create"):
            game_id = str(uuid.uuid4())[:6]
            create_game(game_id, chat_id)

            send(chat_id,
                 f"🎯 کد بازی:\n{game_id}",
                 copy_button(game_id)
            )

        # JOIN
        elif text.startswith("/join"):
            parts = text.split()
            if len(parts) < 2:
                send(chat_id, "❌ /join GAME_ID")
                return "ok"

            game_id = parts[1]
            game = get_game(game_id)

            if not game:
                send(chat_id, "❌ بازی پیدا نشد")
                return "ok"

            if game["p2"]:
                send(chat_id, "❌ بازی پر است")
                return "ok"

            game["p2"] = chat_id
            update_game(game)

            send(game["p1"], "🎮 حریف وصل شد!")
            send(game["p2"], "🎮 بازی شروع شد!")

            send(game["p1"], "نوبت شما", choice_buttons())
            send(game["p2"], "نوبت شما", choice_buttons())

    # ---------------- CALLBACK ----------------
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        move = cq["data"]

        # پیدا کردن بازی
        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()

        if not row:
            return "ok"

        game = get_game(row[0])

        if not game:
            return "ok"

        # تعیین بازیکن
        if chat_id == game["p1"]:
            if game["p1_move"]:
                send(chat_id, "⚠️ قبلاً انتخاب کردی")
                return "ok"
            game["p1_move"] = move
        else:
            if game["p2_move"]:
                send(chat_id, "⚠️ قبلاً انتخاب کردی")
                return "ok"
            game["p2_move"] = move

        update_game(game)

        # وقتی هر دو انتخاب کردند
        if game["p1_move"] and game["p2_move"]:

            r = winner(game["p1_move"], game["p2_move"])

            if r == 1:
                game["p1_score"] += 1
                send(game["p1"], "شما یک امتیاز گرفتید")
                send(game["p2"], "حریف شما یک امتیاز گرفت")

            elif r == 2:
                game["p2_score"] += 1
                send(game["p2"], "شما یک امتیاز گرفتید")
                send(game["p1"], "حریف شما یک امتیاز گرفت")

            else:
                send(game["p1"], "🤝 مساوی")
                send(game["p2"], "🤝 مساوی")

            # reset moves
            game["p1_move"] = None
            game["p2_move"] = None
            game["round"] += 1

            update_game(game)

            # ادامه بازی
            send(game["p1"], "راند بعد", choice_buttons())
            send(game["p2"], "راند بعد", choice_buttons())

    return "ok"


# ================= RUN =================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
