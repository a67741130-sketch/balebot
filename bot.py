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
        "inline_keyboard": [[
            {"text": "✊ سنگ", "callback_data": "rock"},
            {"text": "✋ کاغذ", "callback_data": "paper"},
            {"text": "✌️ قیچی", "callback_data": "scissors"}
        ]]
    }


# ---------------- COPY BUTTON (GAME CODE) ----------------
def copy_button(code):
    return {
        "inline_keyboard": [[
            {"text": f"📋 کپی کد بازی: {code}", "callback_data": f"copy_{code}"}
        ]]
    }


# ---------------- USER LABEL ----------------
def user_label(game, player_key):
    pid = game[player_key]
    return str(pid)


# ---------------- WIN LOGIC ----------------
def round_winner(m1, m2):
    if m1 == m2:
        return 0
    if (m1 == "rock" and m2 == "scissors") or \
       (m1 == "paper" and m2 == "rock") or \
       (m1 == "scissors" and m2 == "paper"):
        return 1
    return 2


# ---------------- INIT GAME ----------------
def init_game(p1):
    return {
        "p1": p1,
        "p2": None,
        "moves": {},
        "score": {"p1": 0, "p2": 0},
        "round": 1,
        "max_rounds": 3
    }


# ---------------- WEBHOOK ----------------
@app.route("/", methods=["POST"])
def webhook():

    data = request.get_json(force=True)
    print("UPDATE:", data)

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
            games[game_id] = init_game(chat_id)
            user_game[chat_id] = game_id

            send(chat_id,
                 f"🎯 بازی ساخته شد\nکد: {game_id}",
                 copy_button(game_id)
            )

        # JOIN
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

            send(game["p1"], "🎮 حریف وصل شد!")
            send(game["p2"], "🎮 شروع بازی!")

            send(game["p1"], f"راند {game['round']}", choice_buttons())
            send(game["p2"], f"راند {game['round']}", choice_buttons())

    # ---------------- CALLBACK ----------------
    if "callback_query" in data:
        cq = data["callback_query"]
        chat_id = cq["message"]["chat"]["id"]
        move = cq["data"]

        # COPY BUTTON
        if move.startswith("copy_"):
            return "ok"

        if chat_id not in user_game:
            send(chat_id, "❌ وارد بازی نیستی")
            return "ok"

        game_id = user_game[chat_id]
        game = games.get(game_id)

        if not game or not game["p2"]:
            return "ok"

        # جلوگیری از دوبار انتخاب
        if chat_id in game["moves"]:
            send(chat_id, "⚠️ قبلاً انتخاب کردی")
            return "ok"

        if chat_id == game["p1"]:
            game["moves"]["p1"] = move
        else:
            game["moves"]["p2"] = move

        send(chat_id, f"ثبت شد: {move}")

        # اگر هر دو حرکت کردند
        if "p1" in game["moves"] and "p2" in game["moves"]:

            r = round_winner(game["moves"]["p1"], game["moves"]["p2"])

            p1 = user_label(game, "p1")
            p2 = user_label(game, "p2")

            if r == 1:
                game["score"]["p1"] += 1
                msg = f"🏆 برنده این راند: {p1}"
            elif r == 2:
                game["score"]["p2"] += 1
                msg = f"🏆 برنده این راند: {p2}"
            else:
                msg = "🤝 مساوی"

            send(game["p1"], msg)
            send(game["p2"], msg)

            game["moves"] = {}
            game["round"] += 1

            # پایان بازی
            if game["round"] > game["max_rounds"]:

                final = (
                    f"🎮 پایان بازی\n\n"
                    f"{p1}: {game['score']['p1']}\n"
                    f"{p2}: {game['score']['p2']}"
                )

                send(game["p1"], final)
                send(game["p2"], final)

            else:
                send(game["p1"], f"راند {game['round']}", choice_buttons())
                send(game["p2"], f"راند {game['round']}", choice_buttons())

    return "ok"


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
