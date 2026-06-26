import json
import random
from telebot import types

QUIZ_STATE = {}

LETTERS = ["A", "B", "C", "D"]


# =========================
# GENERATE QUIZ (AI)
# =========================

def generate_quiz(ask_ai, user_id, topic, amount=5):
    prompt = f"""
Create a JSON quiz in Russian about: {topic}

Return ONLY JSON in this format:
{{
  "title": "{topic}",
  "questions": [
    {{
      "question": "...",
      "options": ["A", "B", "C", "D"],
      "correct": 0,
      "explanation": "..."
    }}
  ]
}}

Make EXACTLY {amount} questions.
No markdown, no text outside JSON.
"""

    txt = ask_ai(user_id, prompt).strip()

    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]

    return json.loads(txt)


# =========================
# TEXT BUILDERS
# =========================

def _progress(i, total):
    bar = int((i / total) * 10)
    return "▓" * bar + "░" * (10 - bar)


def _question_text(st):
    q = st["quiz"]["questions"][st["i"]]
    total = len(st["quiz"]["questions"])

    return (
        f"🧠 <b>{st['quiz']['title']}</b>\n"
        f"{_progress(st['i'], total)} {st['i']+1}/{total}\n\n"
        f"❓ <b>{q['question']}</b>"
    )


# =========================
# KEYBOARD
# =========================

def _question_keyboard(chat_id, st):
    q = st["quiz"]["questions"][st["i"]]

    kb = types.InlineKeyboardMarkup(row_width=2)

    for idx, opt in enumerate(q["options"]):
        letter = LETTERS[idx]

        kb.add(
            types.InlineKeyboardButton(
                f"{letter}. {opt}",
                callback_data=f"q:{chat_id}:{st['i']}:{idx}"
            )
        )

    return kb


def _next_keyboard(chat_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➡️ Далее", callback_data=f"next:{chat_id}")
    )
    return kb


def _final_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🔄 Ещё раз", callback_data="quiz:restart"),
        types.InlineKeyboardButton("🏠 Меню", callback_data="menu:main"),
    )
    return kb


# =========================
# RESULT
# =========================

def _result_text(st):
    total = len(st["quiz"]["questions"])
    score = st["score"]
    percent = int((score / total) * 100)

    if percent == 100:
        msg = "🏆 Идеально!"
    elif percent >= 70:
        msg = "🎉 Отлично!"
    elif percent >= 40:
        msg = "🙂 Неплохо!"
    else:
        msg = "📚 Нужно повторить"

    return (
        f"🎮 <b>Квиз завершён!</b>\n\n"
        f"🏅 Результат: {score}/{total} ({percent}%)\n"
        f"{msg}"
    )


# =========================
# START QUIZ
# =========================

def start_quiz(bot, ask_ai, message, topic, amount=5):
    chat_id = message.chat.id

    wait = bot.send_message(chat_id, "⏳ Генерирую квиз...")

    try:
        quiz = generate_quiz(ask_ai, message.from_user.id, topic, amount)
    except Exception:
        bot.edit_message_text("❌ Ошибка генерации квиза", chat_id, wait.message_id)
        return

    QUIZ_STATE[chat_id] = {
        "quiz": quiz,
        "i": 0,
        "score": 0,
        "answered": False,
    }

    send_question(bot, chat_id)


# =========================
# SEND QUESTION
# =========================

def send_question(bot, chat_id):
    st = QUIZ_STATE.get(chat_id)
    if not st:
        return

    if st["i"] >= len(st["quiz"]["questions"]):
        bot.send_message(
            chat_id,
            _result_text(st),
            reply_markup=_final_keyboard(),
            parse_mode="HTML"
        )
        del QUIZ_STATE[chat_id]
        return

    st["answered"] = False

    bot.send_message(
        chat_id,
        _question_text(st),
        parse_mode="HTML",
        reply_markup=_question_keyboard(chat_id, st)
    )


# =========================
# HANDLE ANSWER
# =========================

def handle_answer(bot, call):
    _, chat_id, q_i, opt_i = call.data.split(":")
    chat_id, q_i, opt_i = int(chat_id), int(q_i), int(opt_i)

    st = QUIZ_STATE.get(chat_id)
    if not st:
        return

    if st["i"] != q_i:
        return

    if st["answered"]:
        return

    st["answered"] = True

    q = st["quiz"]["questions"][st["i"]]
    correct = q["correct"]

    if opt_i == correct:
        st["score"] += 1
        bot.answer_callback_query(call.id, "✅ Верно!")
    else:
        bot.answer_callback_query(call.id, "❌ Неверно")

    text = (
        f"❓ {q['question']}\n\n"
        f"✔️ Правильный ответ: {q['options'][correct]}\n"
    )

    bot.edit_message_text(
        text,
        chat_id,
        call.message.message_id,
        reply_markup=_next_keyboard(chat_id)
    )


# =========================
# NEXT QUESTION
# =========================

def next_question(bot, call):
    chat_id = int(call.data.split(":")[1])

    st = QUIZ_STATE.get(chat_id)
    if not st:
        return

    st["i"] += 1
    send_question(bot, chat_id)


# =========================
# REGISTER
# =========================

def register(bot, ask_ai):

    @bot.callback_query_handler(func=lambda c: c.data.startswith("q:"))
    def answer(call):
        handle_answer(bot, call)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("next:"))
    def nxt(call):
        next_question(bot, call)
        bot.answer_callback_query(call.id)