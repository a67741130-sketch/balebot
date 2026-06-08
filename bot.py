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


# ---------------- WIN LOGIC ----------------
def round_winner(p1_move, p2_move):
    if p1_move == p2_move:
        return 0

    if (p1_move == "rock" and p2_move == "scissors") or \
       (p1_move == "paper" and p2_move == "rock") or \
       (p1_move == "scissors" and p2_move == "paper"):
        return 1

    return 2


# ---------------- GAME INIT ----------------
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
            send(chat_id, "🎮 آماده‌ای؟\n/create برای شروع بازی")

        # CREATE
        elif text.startswith("/create"):
            game_id = str(uuid.uuid4())[:6]
            games[game_id] = init_game(chat_id)
            user_game[chat_id] = game_id

            send(chat_id, f"🎯 بازی ساخته شد\nکد: {game_id}\nمنتظر حریف...")

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

        if chat_id not in user_game:
            send(chat_id, "❌ وارد بازی نیستی")
            return "ok"

        game_id = user_game[chat_id]
        game = games.get(game_id)

        if not game or not game["p2"]:
            return "ok"

        # جلوگیری از دوبار انتخاب
        if chat_id in game["moves"]:
            send(chat_id, "⚠️ تو این راند انتخاب کردی")
            return "ok"

        if chat_id == game["p1"]:
            game["moves"]["p1"] = move
        else:
            game["moves"]["p2"] = move

        send(chat_id, f"ثبت شد: {move}")

        # اگر هر دو انتخاب کردند
        if "p1" in game["moves"] and "p2" in game["moves"]:

            result = round_winner(game["moves"]["p1"], game["moves"]["p2"])

            if result == 1:
                game["score"]["p1"] += 1
                msg = "🏆 بازیکن 1 برد این راند"
            elif result == 2:
                game["score"]["p2"] += 1
                msg = "🏆 بازیکن 2 برد این راند"
            else:
                msg = "🤝 مساوی"

            send(game["p1"], msg)
            send(game["p2"], msg)

            # پاک کردن حرکت‌ها
            game["moves"] = {}

            game["round"] += 1

            # پایان بازی
            if game["round"] > game["max_rounds"]:

                if game["score"]["p1"] > game["score"]["p2"]:
                    final = "🎉 Player 1 برنده کل بازی شد"
                elif game["score"]["p2"] > game["score"]["p1"]:
                    final = "🎉 Player 2 برنده کل بازی شد"
                else:
                    final = "🤝 بازی مساوی شد"

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
