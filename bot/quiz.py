import json
from telebot import types

QUIZ_STATE = {}

LETTERS = ["🅰️", "🅱️", "🅲️", "🅳️", "🅴", "🅵"]


# ─────────────────────────────────────────────
# Генерация квиза
# ─────────────────────────────────────────────

def generate_quiz(ask_ai, user_id, topic):
    prompt = f"""Create a JSON quiz about: {topic}
Return ONLY JSON:
{{"title":"...","questions":[{{"question":"...","options":["","","",""],"correct":0,"explanation":"..."}}]}}"""

    txt = ask_ai(user_id, prompt).strip()

    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]

    return json.loads(txt)


# ─────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────

def _progress_bar(current, total, length=10):
    if total == 0:
        return ""
    filled = round(length * current / total)
    return "▓" * filled + "░" * (length - filled)


def _build_question_text(st):
    quiz = st["quiz"]
    q = quiz["questions"][st["i"]]
    total = len(quiz["questions"])

    bar = _progress_bar(st["i"], total)

    return (
        f"📚 <b>{quiz.get('title','Квиз')}</b>\n"
        f"{bar} <i>{st['i']+1}/{total}</i>\n\n"
        f"❓ <b>{q['question']}</b>"
    )


# ─────────────────────────────────────────────
# Кнопки вопроса
# ─────────────────────────────────────────────

def _build_keyboard(chat_id, st):
    q = st["quiz"]["questions"][st["i"]]

    kb = types.InlineKeyboardMarkup(row_width=2)

    buttons = []
    for idx, opt in enumerate(q["options"]):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)

        buttons.append(
            types.InlineKeyboardButton(
                text=letter,
                callback_data=f"quiz:{chat_id}:{st['i']}:{idx}",
            )
        )

    kb.add(*buttons)
    return kb


# ─────────────────────────────────────────────
# Кнопки результата
# ─────────────────────────────────────────────

def _build_result_keyboard(chat_id, st, selected, correct):
    q = st["quiz"]["questions"][st["i"]]
    kb = types.InlineKeyboardMarkup(row_width=2)

    buttons = []

    for idx, _ in enumerate(q["options"]):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)

        if idx == correct:
            text = f"{letter} ✔️"
        elif idx == selected:
            text = f"{letter} ❌"
        else:
            text = f"{letter}"

        buttons.append(
            types.InlineKeyboardButton(text=text, callback_data="noop")
        )

    kb.add(*buttons)

    kb.row(
        types.InlineKeyboardButton("➡️ Далее", callback_data=f"quiz_next:{chat_id}")
    )

    return kb


# ─────────────────────────────────────────────
# Ответ пользователя
# ─────────────────────────────────────────────

def handle_answer(bot, call):
    try:
        _, chat_id_s, q_idx_s, opt_idx_s = call.data.split(":")
        chat_id, q_idx, opt_idx = int(chat_id_s), int(q_idx_s), int(opt_idx_s)
    except:
        bot.answer_callback_query(call.id, "Ошибка данных")
        return

    st = QUIZ_STATE.get(chat_id)
    if not st:
        return

    if q_idx != st["i"]:
        bot.answer_callback_query(call.id, "Устаревший вопрос")
        return

    if st["answered"]:
        bot.answer_callback_query(call.id, "Уже отвечено")
        return

    st["answered"] = True

    q = st["quiz"]["questions"][st["i"]]
    correct = q["correct"]

    if opt_idx == correct:
        st["score"] += 1
        bot.answer_callback_query(call.id, "✅ Верно!")
    else:
        bot.answer_callback_query(call.id, "❌ Неверно")

    result_text = build_result_text(q, opt_idx, correct)

    bot.edit_message_text(
        result_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode="HTML",
        reply_markup=_build_result_keyboard(chat_id, st, opt_idx, correct)
    )


def build_result_text(q, selected, correct):
    is_correct = selected == correct

    lines = [
        "✅ <b>Верно!</b>" if is_correct else "❌ <b>Неверно</b>",
        "",
        f"❓ {q['question']}",
        ""
    ]

    for idx, opt in enumerate(q["options"]):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)

        mark = ""
        if idx == correct:
            mark = " ✔️"
        elif idx == selected:
            mark = " ❌"

        lines.append(f"{letter} {opt}{mark}")

    if q.get("explanation"):
        lines += ["", f"💡 <i>{q['explanation']}</i>"]

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Переход к следующему вопросу
# ─────────────────────────────────────────────

def send_next(bot, chat_id):
    st = QUIZ_STATE.get(chat_id)
    if st is None:
        return

    quiz = st["quiz"]

    if st["i"] >= len(quiz["questions"]):
        kb = types.InlineKeyboardMarkup()

        kb.row(
            types.InlineKeyboardButton("🔄 Новый квиз", callback_data="menu:quiz"),
            types.InlineKeyboardButton("🏠 Меню", callback_data="menu:main"),
        )

        bot.send_message(
            chat_id,
            build_final_text(st),
            parse_mode="HTML",
            reply_markup=kb
        )

        del QUIZ_STATE[chat_id]
        return

    q = quiz["questions"][st["i"]]

    text = (
        f"📚 <b>{quiz.get('title','Квиз')}</b>\n\n"
        f"❓ <b>{q['question']}</b>"
    )

    bot.send_message(
        chat_id,
        text,
        parse_mode="HTML",
        reply_markup=_build_keyboard(chat_id, st)
    )


def next_question(bot, chat_id):
    st = QUIZ_STATE.get(chat_id)
    if not st:
        return

    st["i"] += 1
    st["answered"] = False

    send_next(bot, chat_id)


# ─────────────────────────────────────────────
# Финальный экран
# ─────────────────────────────────────────────

def build_final_text(st):
    total = len(st["quiz"]["questions"])
    score = st["score"]
    pct = round(100 * score / total) if total else 0

    if pct == 100:
        emoji = "🏆"
        msg = "Идеально!"
    elif pct >= 70:
        emoji = "🎉"
        msg = "Отличный результат!"
    elif pct >= 40:
        emoji = "🙂"
        msg = "Неплохо!"
    else:
        emoji = "📖"
        msg = "Стоит повторить тему."

    return (
        f"{emoji} <b>Квиз завершён!</b>\n\n"
        f"Результат: <b>{score}/{total}</b> ({pct}%)\n"
        f"{msg}"
    )


# ─────────────────────────────────────────────
# Регистрация
# ─────────────────────────────────────────────

def register(bot, ask_ai):

    @bot.message_handler(commands=["quiz"])
    def quiz_cmd(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Использование: /quiz <тема>")
            return

        topic = parts[1]
        chat_id = message.chat.id

        wait = bot.send_message(chat_id, f"⏳ Генерирую квиз по теме «{topic}»...")

        try:
            quiz = generate_quiz(ask_ai, message.from_user.id, topic)
        except:
            bot.edit_message_text(
                "⚠️ Не удалось сгенерировать квиз.",
                chat_id,
                wait.message_id
            )
            return

        QUIZ_STATE[chat_id] = {
            "quiz": quiz,
            "i": 0,
            "score": 0,
            "answered": False,
        }

        send_next(bot, chat_id)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("quiz:"))
    def callback_handler(call):
        handle_answer(bot, call)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("quiz_next:"))
    def next_handler(call):
        chat_id = int(call.data.split(":")[1])
        next_question(bot, chat_id)