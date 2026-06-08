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
conn = sqlite3.connect("vc_games.db", check_same_thread=False)
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
    status TEXT
)
""")
conn.commit()


# ================= STATE (simple memory) =================
user_state = {}  # waiting_for_code


# ================= SEND =================
def send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(BASE_URL + "/sendMessage", data=data)


# ================= UI =================
def main_menu():
    return {
        "inline_keyboard": [[
            {"text": "🆕 ساخت بازی", "callback_data": "create"},
            {"text": "🔗 ورود به بازی", "callback_data": "join"}
        ]]
    }


def copy_button(code):
    return {
        "inline_keyboard": [[
            {"text": "📋 کپی کد بازی", "switch_inline_query": code}
        ]]
    }


def choice_buttons():
    return {
        "inline_keyboard": [[
            {"text": "✊", "callback_data": "rock"},
            {"text": "✋", "callback_data": "paper"},
            {"text": "✌️", "callback_data": "scissors"}
        ]]
    }


# ================= GAME LOGIC =================
def win(a, b):
    if a == b:
        return 0
    if (a == "rock" and b == "scissors") or \
       (a == "paper" and b == "rock") or \
       (a == "scissors" and b == "paper"):
        return 1
    return 2


def create_game(game_id, p1):
    cur.execute("""
    INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (game_id, p1, None, 0, 0, 1, None, None, "waiting"))
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
        "status": row[8],
    }


def update(game):
    cur.execute("""
    UPDATE games
    SET p2=?, p1_score=?, p2_score=?, round=?, p1_move=?, p2_move=?, status=?
    WHERE game_id=?
    """, (
        game["p2"],
        game["p1_score"],
        game["p2_score"],
        game["round"],
        game["p1_move"],
        game["p2_move"],
        game["status"],
        game["game_id"]
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

        # FIRST ENTRY
        if text == "/start":
            send(chat_id, "🎮 خوش آمدی", main_menu())

        # JOIN MODE
        elif user_state.get(chat_id) == "waiting_code":
            game = get_game(text)

            if not game:
                send(chat_id, "❌ کد اشتباهه")
                return "ok"

            if game["p2"]:
                send(chat_id, "❌ بازی پره")
                return "ok"

            game["p2"] = chat_id
            game["status"] = "playing"
            update(game)

            send(game["p1"], "🎮 حریف وارد شد")
            send(game["p2"], "🎮 بازی شروع شد")

            send(game["p1"], "راند 1", choice_buttons())
            send(game["p2"], "راند 1", choice_buttons())

            user_state.pop(chat_id, None)

        return "ok"

    # ---------------- CALLBACK ----------------
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        action = cq["data"]

        # CREATE GAME
        if action == "create":
            game_id = str(uuid.uuid4())[:6]
            create_game(game_id, chat_id)

            send(chat_id,
                 f"🎯 کد بازی:\n{game_id}",
                 copy_button(game_id)
            )
            return "ok"

        # JOIN GAME
        if action == "join":
            user_state[chat_id] = "waiting_code"
            send(chat_id, "📩 لطفا کد بازی را وارد کنید")
            return "ok"

        # GAME MOVE
        cur.execute("SELECT game_id FROM games WHERE p1=? OR p2=?", (chat_id, chat_id))
        row = cur.fetchone()
        if not row:
            return "ok"

        game = get_game(row[0])

        if chat_id == game["p1"]:
            if game["p1_move"]:
                return "ok"
            game["p1_move"] = action
        else:
            if game["p2_move"]:
                return "ok"
            game["p2_move"] = action

        update(game)

        # BOTH MOVES READY
        if game["p1_move"] and game["p2_move"]:

            r = win(game["p1_move"], game["p2_move"])

            if r == 1:
                game["p1_score"] += 1
                send(game["p1"], "🏆 شما یک امتیاز گرفتید")
                send(game["p2"], "😢 حریف شما یک امتیاز گرفت")
            elif r == 2:
                game["p2_score"] += 1
                send(game["p2"], "🏆 شما یک امتیاز گرفتید")
                send(game["p1"], "😢 حریف شما یک امتیاز گرفت")
            else:
                send(game["p1"], "🤝 مساوی")
                send(game["p2"], "🤝 مساوی")

            game["p1_move"] = None
            game["p2_move"] = None
            game["round"] += 1

            # END GAME (3 ROUNDS FIXED)
            if game["round"] > 3:
                result = (
                    f"🎮 پایان بازی\n\n"
                    f"🏅 شما: {game['p1_score']}\n"
                    f"🏅 حریف: {game['p2_score']}"
                )
                send(game["p1"], result)
                send(game["p2"], result)
                return "ok"

            update(game)

            send(game["p1"], f"راند {game['round']}", choice_buttons())
            send(game["p2"], f"راند {game['round']}", choice_buttons())

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
