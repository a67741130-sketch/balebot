from flask import Flask, request
import requests
import uuid
import json
import os

app = Flask(__name__)

TOKEN = "934745261:DtDGTB3MeeTg2V8-jfUbzr5O2KcQGQi6WXQ"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

games = {}
user_game = {}

# ---------------- SEND ----------------
def send(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    requests.post(BASE_URL + "/sendMessage", data=payload)


# ---------------- BUTTONS ----------------
def choice_buttons():
    return {
        "inline_keyboard": [
            [
                {"text": "✊ سنگ", "callback_data": "rock"},
                {"text": "✋ کاغذ", "callback_data": "paper"},
                {"text": "✌️ قیچی", "callback_data": "scissors"}
            ]
        ]
    }


# ---------------- GAME LOGIC ----------------
def winner(m1, m2):
    if m1 == m2:
        return "🤝 مساوی"

    if (m1 == "rock" and m2 == "scissors") or \
       (m1 == "paper" and m2 == "rock") or \
       (m1 == "scissors" and m2 == "paper"):
        return "🏆 بازیکن 1 برنده شد"

    return "🏆 بازیکن 2 برنده شد"


# ---------------- WEBHOOK ----------------
@app.route("/", methods=["POST"])
def webhook():

    data = request.get_json(force=True)

    print("=== UPDATE RECEIVED ===")
    print(data)

    # ---------------- MESSAGE ----------------
    if "message" in data:
        msg = data["message"]

        text = msg.get("text")
        chat_id = msg["chat"]["id"]

        if not text:
            return "ok"

        text = text.strip()

        # START
        if text.startswith("/start"):
            send(chat_id, "🎮 خوش اومدی!\n/create برای ساخت بازی")

        # CREATE GAME
        elif text.startswith("/create"):
            game_id = str(uuid.uuid4())[:6]

            games[game_id] = {
                "p1": chat_id,
                "p2": None,
                "moves": {}
            }

            user_game[chat_id] = game_id

            send(chat_id, f"🎯 بازی ساخته شد!\nکد: {game_id}\nمنتظر نفر دوم...")

        # JOIN GAME
        elif text.startswith("/join"):
            parts = text.split()

            if len(parts) < 2:
                send(chat_id, "❌ /join GAME_ID")
                return "ok"

            game_id = parts[1]

            if game_id not in games:
                send(chat_id, "❌ بازی پیدا نشد")
                return "ok"

            game = games[game_id]

            game["p2"] = chat_id
            user_game[chat_id] = game_id
            user_game[game["p1"]] = game_id

            send(game["p1"], "🎮 حریف وصل شد!", choice_buttons())
            send(game["p2"], "🎮 شروع بازی!", choice_buttons())

    # ---------------- CALLBACK ----------------
    if "callback_query" in data:
        cq = data["callback_query"]

        chat_id = cq["message"]["chat"]["id"]
        move = cq["data"]

        if chat_id not in user_game:
            send(chat_id, "❌ وارد بازی نیستی")
            return "ok"

        game_id = user_game[chat_id]
        game = games.get(game_id)

        if not game:
            return "ok"

        if chat_id == game["p1"]:
            game["moves"]["p1"] = move
        else:
            game["moves"]["p2"] = move

        send(chat_id, f"ثبت شد: {move}")

        if "p1" in game["moves"] and "p2" in game["moves"]:
            result = winner(game["moves"]["p1"], game["moves"]["p2"])

            send(game["p1"], result)
            send(game["p2"], result)

    return "ok"


# ---------------- RUN (RENDER FIXED PORT) ----------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
