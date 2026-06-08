from flask import Flask, request
import requests
import uuid
import json
import os
import sqlite3

app = Flask(__name__)

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ---------------- DB ----------------
conn = sqlite3.connect("game.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    p1 INTEGER,
    p2 INTEGER,
    p1_score INTEGER,
    p2_score INTEGER,
    round INTEGER
)
""")
conn.commit()


# ---------------- SEND ----------------
def send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    requests.post(BASE_URL + "/sendMessage", data=payload)


# ---------------- COPY BUTTON FIXED ----------------
def copy_button(code):
    return {
        "inline_keyboard": [[
            {
                "text": "📋 کپی کد بازی",
                "switch_inline_query": code
            }
        ]]
    }


# ---------------- GAME LOGIC ----------------
def win(m1, m2):
    if m1 == m2:
        return 0
    if (m1 == "rock" and m2 == "scissors") or \
       (m1 == "paper" and m2 == "rock") or \
       (m1 == "scissors" and m2 == "paper"):
        return 1
    return 2


# ---------------- CREATE GAME ----------------
def create_game(game_id, p1):
    cur.execute("""
    INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)
    """, (game_id, p1, None, 0, 0, 1))
    conn.commit()


# ---------------- UPDATE GAME ----------------
def update_game(game):
    cur.execute("""
    UPDATE games SET p2=?, p1_score=?, p2_score=?, round=?
    WHERE game_id=?
    """, (
        game["p2"],
        game["p1_score"],
        game["p2_score"],
        game["round"],
        game["game_id"]
    ))
    conn.commit()


# ---------------- GET GAME ----------------
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
    }


# ---------------- WEBHOOK ----------------
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
            send(chat_id, "🎮 آماده‌ای؟ /create")

        # CREATE
        elif text.startswith("/create"):
            game_id = str(uuid.uuid4())[:6]
            create_game(game_id, chat_id)

            send(chat_id,
                 f"🎯 کد بازی شما:\n{game_id}",
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
                send(chat_id, "❌ بازی پر شده")
                return "ok"

            game["p2"] = chat_id
            update_game(game)

            send(game["p1"], "🎮 حریف وصل شد!")
            send(game["p2"], "🎮 شروع بازی!")

    return "ok"


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
