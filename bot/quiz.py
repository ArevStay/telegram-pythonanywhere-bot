
"""
quiz.py - AI quiz module (inline-keyboard version)
 
Интеграция с твоим telebot-проектом.
Замени generate_quiz() на свою генерацию через ask_ai, если нужно другое поведение.
"""
import json
from telebot import types
 
QUIZ_STATE = {}
 
LETTERS = ["A", "B", "C", "D", "E", "F"]
 
 
# ──────────────────────────────────────────────────────────────────────────
# Генерация квиза
# ──────────────────────────────────────────────────────────────────────────
 
def generate_quiz(ask_ai, user_id, topic):
    prompt = f"""Create a JSON quiz about: {topic}
Return ONLY JSON, no markdown, no extra text:
{{"title":"...","questions":[{{"question":"...","options":["","","",""],"correct":0,"explanation":"..."}}]}}"""
    txt = ask_ai(user_id, prompt)
    txt = txt.strip()
    # на случай если модель всё же обернула ответ в ```json ... ```
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    return json.loads(txt)
 
 
# ──────────────────────────────────────────────────────────────────────────
# Вспомогательные функции отображения
# ──────────────────────────────────────────────────────────────────────────
 
def _progress_bar(current, total, length=10):
    filled = round(length * current / total)
    return "▓" * filled + "░" * (length - filled)
 
 
def _build_question_text(st):
    quiz = st["quiz"]
    q = quiz["questions"][st["i"]]
    total = len(quiz["questions"])
    bar = _progress_bar(st["i"], total)
 
    lines = [
        f"📚 <b>{quiz.get('title', 'Квиз')}</b>",
        f"{bar}  <i>{st['i'] + 1}/{total}</i>",
        "",
        f"❓ <b>{q['question']}</b>",
        "",
    ]
    for idx, opt in enumerate(q["options"]):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)
        lines.append(f"<b>{letter}.</b> {opt}")
    return "\n".join(lines)
 
 
def _build_keyboard(chat_id, st):
    q = st["quiz"]["questions"][st["i"]]
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for idx, _ in enumerate(q["options"]):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)
        buttons.append(
            types.InlineKeyboardButton(
                text=letter,
                callback_data=f"quiz:{chat_id}:{st['i']}:{idx}",
            )
        )
    kb.add(*buttons)
    return kb
 
 
def _build_result_text(st, q, selected, correct):
    is_correct = selected == correct
    header = "✅ <b>Верно!</b>" if is_correct else "❌ <b>Неверно</b>"
 
    lines = [header, "", f"❓ {q['question']}", ""]
    for idx, opt in enumerate(q["options"]):
        letter = LETTERS[idx] if idx < len(LETTERS) else str(idx + 1)
        marker = ""
        if idx == correct:
            marker = " ✅"
        elif idx == selected and not is_correct:
            marker = " ❌"
        lines.append(f"<b>{letter}.</b> {opt}{marker}")
 
    explanation = q.get("explanation")
    if explanation:
        lines += ["", f"💡 <i>{explanation}</i>"]
 
    return "\n".join(lines)
 
 
def _build_final_text(st):
    total = len(st["quiz"]["questions"])
    score = st["score"]
    pct = round(100 * score / total) if total else 0
 
    if pct == 100:
        emoji = "🏆"
        comment = "Идеально! Ты знаешь тему на отлично."
    elif pct >= 70:
        emoji = "🎉"
        comment = "Отличный результат!"
    elif pct >= 40:
        emoji = "🙂"
        comment = "Неплохо, но есть куда расти."
    else:
        emoji = "📖"
        comment = "Стоит повторить тему."
 
    title = st["quiz"].get("title", "Квиз")
    return (
        f"{emoji} <b>Квиз «{title}» завершён!</b>\n\n"
        f"Результат: <b>{score}/{total}</b> ({pct}%)\n"
        f"{comment}"
    )
 
 
# ──────────────────────────────────────────────────────────────────────────
# Логика квиза
# ──────────────────────────────────────────────────────────────────────────
 
def start_quiz(bot, ask_ai, message, topic):
    chat_id = message.chat.id
    wait_msg = bot.send_message(chat_id, f"⏳ Генерирую квиз по теме «{topic}»...")
    try:
        quiz = generate_quiz(ask_ai, message.from_user.id, topic)
    except Exception:
        bot.edit_message_text(
            "⚠️ Не удалось сгенерировать квиз. Попробуй другую тему или повтори позже.",
            chat_id, wait_msg.message_id,
        )
        return
 
    if not quiz.get("questions"):
        bot.edit_message_text("⚠️ Квиз получился пустым. Попробуй другую тему.", chat_id, wait_msg.message_id)
        return
 
    QUIZ_STATE[chat_id] = {
        "quiz": quiz,
        "i": 0,
        "score": 0,
        "answered": False,
        "msg_id": wait_msg.message_id,
    }
    send_next(bot, chat_id)
 
 
def send_next(bot, chat_id):
    st = QUIZ_STATE.get(chat_id)
    if st is None:
        return
 
    if st["i"] >= len(st["quiz"]["questions"]):
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.row(
            types.InlineKeyboardButton("🔄 Новый квиз", callback_data="menu:quiz"),
            types.InlineKeyboardButton("🏠 Меню", callback_data="menu:main"),
        )
        bot.send_message(chat_id, _build_final_text(st), parse_mode="HTML", reply_markup=kb)
        del QUIZ_STATE[chat_id]
        return
 
    st["answered"] = False
    text = _build_question_text(st)
    kb = _build_keyboard(chat_id, st)
 
    sent = bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)
    st["msg_id"] = sent.message_id
 
 
def handle_answer(bot, call):
    """call.data format: quiz:<chat_id>:<question_index>:<option_index>"""
    try:
        _, chat_id_s, q_idx_s, opt_idx_s = call.data.split(":")
        chat_id, q_idx, opt_idx = int(chat_id_s), int(q_idx_s), int(opt_idx_s)
    except (ValueError, AttributeError):
        bot.answer_callback_query(call.id, "Ошибка данных")
        return
 
    st = QUIZ_STATE.get(chat_id)
    if st is None:
        bot.answer_callback_query(call.id, "⏱ Квиз уже завершён или истёк.")
        return
 
    if q_idx != st["i"]:
        bot.answer_callback_query(call.id, "Этот вопрос уже неактуален.")
        return
 
    if st["answered"]:
        bot.answer_callback_query(call.id, "Ты уже ответил на этот вопрос ✅")
        return
 
    st["answered"] = True
    q = st["quiz"]["questions"][st["i"]]
    correct = q["correct"]
 
    if opt_idx == correct:
        st["score"] += 1
        bot.answer_callback_query(call.id, "✅ Верно!")
    else:
        bot.answer_callback_query(call.id, "❌ Неверно")
 
    result_text = _build_result_text(st, q, opt_idx, correct)
    try:
        bot.edit_message_text(
            result_text, chat_id, call.message.message_id,
            parse_mode="HTML",
        )
    except Exception:
        bot.send_message(chat_id, result_text, parse_mode="HTML")
 
    st["i"] += 1
    send_next(bot, chat_id)
 
 
# ──────────────────────────────────────────────────────────────────────────
# Регистрация хендлеров
# ──────────────────────────────────────────────────────────────────────────
 
def register(bot, ask_ai):
    @bot.message_handler(commands=["quiz"])
    def quiz_cmd(message):
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Использование: /quiz <тема>")
            return
        start_quiz(bot, ask_ai, message, parts[1])
 
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("quiz:"))
    def callback_handler(call):
        handle_answer(bot, call)