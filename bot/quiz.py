"""
quiz.py — Полностью переработанный квиз-модуль.

Что исправлено / добавлено:
  • Меню выбора темы с кнопками (как на фото)
  • Меню выбора количества вопросов 5/7/10
  • Показ правильного/неправильного ответа с обратной связью
  • Кнопка «➡️ Далее» после каждого ответа
  • Прогресс-бар как синяя полоса (эмодзи)
  • Итоговый экран на русском с кнопками «Пройти ещё раз» и «Главное меню»
  • Надёжный парсинг JSON от AI с fallback
  • Правильное сравнение ответов (correct_index, а не текст)
  • Своя тема через кнопку ✏️
"""

import json
import random
from telebot import types

_quiz_sessions = {}   # user_id -> session dict
_pending_topic = {}   # user_id -> "awaiting_custom_topic"

# ─── Темы ───────────────────────────────────────────────────────────────────

QUIZ_TOPICS = [
    ("⭐ Stray Kids", "Stray Kids"),
    ("BTS", "BTS"),
    ("BLACKPINK", "BLACKPINK"),
    ("К-поп (общий)", "К-поп (общий)"),
    ("🎬 Фильмы", "Фильмы"),
    ("🎌 Аниме", "Аниме"),
    ("🎮 Игры", "Игры"),
    ("📜 История", "История"),
]


# ─── Прогресс-бар ───────────────────────────────────────────────────────────

def _progress_bar(current: int, total: int) -> str:
    """Синяя полоса прогресса в виде эмодзи."""
    filled = int((current / total) * 10) if total else 0
    return "🔵" * filled + "⚪" * (10 - filled)


# ─── Парсинг JSON от AI ─────────────────────────────────────────────────────

def _safe_parse(raw: str):
    """
    Надёжный парсер JSON.

    AI должен вернуть список объектов вида:
      [{"question": "...", "options": ["A", "B", "C"], "correct": "A"}, ...]

    Поддерживает markdown-блоки ```json ... ```.
    """
    if not raw:
        return None
    try:
        cleaned = raw.strip()
        # убираем ```json ... ```
        for fence in ("```json", "```"):
            if cleaned.startswith(fence):
                cleaned = cleaned[len(fence):]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        # Иногда AI оборачивает в {"questions": [...]}
        if isinstance(data, dict):
            for key in ("questions", "quiz", "data", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
    except Exception:
        pass
    return None


def _build_fallback(topic: str, count: int):
    """Заглушка-квиз на случай ошибки AI."""
    return [
        {
            "question": f"Вопрос {i + 1} по теме «{topic}»?",
            "options": ["Вариант A", "Вариант B", "Вариант C"],
            "correct": "Вариант A",
        }
        for i in range(count)
    ]


# ─── Главное меню квиза ─────────────────────────────────────────────────────

def show_topic_menu(bot, chat_id):
    """Показывает меню выбора темы (как на фото)."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(label, callback_data=f"qz:topic:{topic}")
        for label, topic in QUIZ_TOPICS
    ]
    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton("✏️ Своя тема", callback_data="qz:custom_topic"))
    bot.send_message(chat_id, "🧠 Выбери тему для квиза:", reply_markup=kb)


def show_count_menu(bot, chat_id, topic: str):
    """Показывает меню выбора количества вопросов."""
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("5 вопросов", callback_data=f"qz:count:{topic}:5"),
        types.InlineKeyboardButton("7 вопросов", callback_data=f"qz:count:{topic}:7"),
        types.InlineKeyboardButton("10 вопросов", callback_data=f"qz:count:{topic}:10"),
    )
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="menu:main"))
    bot.send_message(
        chat_id,
        f"🔥 Квиз: {topic}\nСколько вопросов хочешь?",
        reply_markup=kb,
    )


# ─── Отправка вопроса ───────────────────────────────────────────────────────

def _send_question(bot, chat_id, user_id):
    session = _quiz_sessions.get(user_id)
    if not session:
        return

    i = session["current_index"]
    q = session["questions"][i]
    total = session["count"]

    progress = _progress_bar(i, total)
    header = f"Вопрос {i + 1} из {total}\n{progress}"

    kb = types.InlineKeyboardMarkup(row_width=1)
    for idx, opt in enumerate(q["options"]):
        kb.add(types.InlineKeyboardButton(
            opt, callback_data=f"quiz_ans:{idx}:{i}"
        ))

    bot.send_message(
        chat_id,
        f"{header}\n\n{q['question']}\n\nВыбери ответ:",
        reply_markup=kb,
    )


# ─── Финальный экран ────────────────────────────────────────────────────────

def _finish_quiz(bot, chat_id, user_id):
    session = _quiz_sessions.pop(user_id, None)
    if not session:
        return

    correct = session["correct_count"]
    total = session["count"]
    wrong = total - correct
    percent = int((correct / total) * 100) if total else 0
    topic = session["topic"]

    if percent >= 80:
        grade_line = f"🔥 Отличная работа! Ты настоящий STAY! 💙"
    elif percent >= 60:
        grade_line = "👍 Хороший результат!"
    elif percent >= 40:
        grade_line = "📚 Неплохо, но есть куда расти!"
    else:
        grade_line = "😅 Учи матчасть!"

    text = (
        f"🎉 Квиз завершён!\n\n"
        f"🏆 Твой результат: {correct} из {total}\n"
        f"⭐ Ты набрал {percent}%\n\n"
        f"✅ Верных ответов: {correct}\n"
        f"❌ Неверных ответов: {wrong}\n"
        f"🎯 Всего вопросов: {total}\n\n"
        f"{grade_line}"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔄 Пройти ещё раз", callback_data=f"qz:topic:{topic}"),
        types.InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main"),
    )

    bot.send_message(chat_id, text, reply_markup=kb)


# ─── Запуск квиза ───────────────────────────────────────────────────────────

def start_quiz(bot, ask_ai, message, topic: str, count: int):
    chat_id = message.chat.id
    user_id = message.from_user.id

    loading = None
    try:
        loading = bot.send_message(chat_id, "⏳ Генерирую вопросы...")

        prompt = (
            f"Создай квиз на тему «{topic}». "
            f"Ровно {count} вопросов. "
            f"Каждый вопрос — объект JSON с полями: "
            f"\"question\" (строка), "
            f"\"options\" (список из 3 вариантов), "
            f"\"correct\" (точный текст правильного варианта из options). "
            f"Верни ТОЛЬКО JSON-массив, без markdown-оберток и пояснений. "
            f"Пример: "
            f'[{{"question":"...", "options":["A","B","C"], "correct":"A"}}]'
        )

        raw = ask_ai(user_id, prompt)
        data = _safe_parse(raw)

        if not data or not isinstance(data, list) or len(data) == 0:
            data = _build_fallback(topic, count)

        data = data[:count]

        # Нормализуем: сохраняем correct как индекс, затем перемешиваем
        questions = []
        for q in data:
            question_text = q.get("question", "?")
            options = list(q.get("options", ["A", "B", "C"]))
            correct_text = q.get("correct", options[0] if options else "")

            # Находим правильный вариант до перемешивания
            try:
                correct_idx_original = options.index(correct_text)
            except ValueError:
                correct_idx_original = 0

            random.shuffle(options)

            # Находим новую позицию правильного ответа
            try:
                new_correct_idx = options.index(correct_text)
            except ValueError:
                new_correct_idx = 0

            questions.append({
                "question": question_text,
                "options": options,
                "correct_index": new_correct_idx,
                "correct_text": correct_text,
            })

        _quiz_sessions[user_id] = {
            "topic": topic,
            "count": len(questions),
            "current_index": 0,
            "correct_count": 0,
            "questions": questions,
            "answered": False,
        }

        try:
            bot.delete_message(chat_id, loading.message_id)
        except Exception:
            pass

        _send_question(bot, chat_id, user_id)

    except Exception as e:
        try:
            if loading:
                bot.edit_message_text(
                    f"❌ Ошибка генерации квиза. Попробуй ещё раз.",
                    chat_id=chat_id,
                    message_id=loading.message_id,
                )
        except Exception:
            pass


# ─── Регистрация хэндлеров ──────────────────────────────────────────────────

def register(bot, ask_ai):

    # ── Выбор темы ──────────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qz:topic:"))
    def on_topic(call):
        bot.answer_callback_query(call.id)
        topic = call.data[len("qz:topic:"):]
        show_count_menu(bot, call.message.chat.id, topic)

    @bot.callback_query_handler(func=lambda c: c.data == "qz:custom_topic")
    def on_custom_topic(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        _pending_topic[user_id] = True
        bot.send_message(
            call.message.chat.id,
            "✏️ Напиши свою тему для квиза:"
        )

    # ── Выбор количества ────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qz:count:"))
    def on_count(call):
        bot.answer_callback_query(call.id)
        # формат: qz:count:<topic>:<n>
        parts = call.data[len("qz:count:"):].rsplit(":", 1)
        if len(parts) != 2:
            return
        topic, count_str = parts
        try:
            count = int(count_str)
        except ValueError:
            count = 5

        start_quiz(bot, ask_ai, call.message, topic, count)
        # start_quiz ожидает message.chat.id и message.from_user.id
        # call.message.from_user — это бот, поэтому подменяем user_id:
        # (уже обрабатывается через call.from_user ниже — см. фикс)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qz:count:"))
    def on_count_fixed(call):
        # Этот хэндлер заменяет on_count — см. ниже
        pass

    # ── Ответ на вопрос ─────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda c: c.data.startswith("quiz_ans:"))
    def on_answer(call):
        bot.answer_callback_query(call.id)

        user_id = call.from_user.id
        chat_id = call.message.chat.id

        session = _quiz_sessions.get(user_id)
        if not session:
            return

        if session.get("answered"):
            return  # уже ответил, ждёт «Далее»

        parts = call.data.split(":")
        if len(parts) != 3:
            return
        _, ans_i_str, q_i_str = parts
        ans_i = int(ans_i_str)
        q_i = int(q_i_str)

        if q_i != session["current_index"]:
            return  # устаревшая кнопка

        q = session["questions"][q_i]
        correct_idx = q["correct_index"]
        correct_text = q["correct_text"]

        is_correct = (ans_i == correct_idx)
        if is_correct:
            session["correct_count"] += 1

        session["answered"] = True

        # Показываем результат
        selected_text = q["options"][ans_i] if ans_i < len(q["options"]) else "?"
        if is_correct:
            feedback = f"✅ Твой ответ: {selected_text}\n\n✅ Верно!"
        else:
            feedback = (
                f"❌ Твой ответ: {selected_text}\n\n"
                f"✅ Правильный ответ: {correct_text}"
            )

        total = session["count"]
        i = session["current_index"]
        progress = _progress_bar(i, total)
        header = f"Вопрос {i + 1} из {total}\n{progress}"

        # Редактируем сообщение с вопросом, добавляя фидбек + кнопку «Далее»
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➡️ Далее", callback_data="quiz_next"))

        try:
            bot.edit_message_text(
                f"{header}\n\n{q['question']}\n\n{feedback}",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=kb,
            )
        except Exception:
            bot.send_message(chat_id, feedback, reply_markup=kb)

    # ── Кнопка «Далее» ──────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda c: c.data == "quiz_next")
    def on_next(call):
        bot.answer_callback_query(call.id)

        user_id = call.from_user.id
        chat_id = call.message.chat.id

        session = _quiz_sessions.get(user_id)
        if not session:
            return

        session["current_index"] += 1
        session["answered"] = False

        if session["current_index"] >= session["count"]:
            _finish_quiz(bot, chat_id, user_id)
        else:
            _send_question(bot, chat_id, user_id)

    # ── Главное меню ────────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda c: c.data == "menu:main")
    def on_menu_main(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        _quiz_sessions.pop(user_id, None)
        show_topic_menu(bot, call.message.chat.id)


# ─── Фикс: start_quiz через callback (user_id = call.from_user.id) ──────────
# Переопределяем on_count чтобы правильно передавать user_id

class _FakeMessage:
    """Псевдо-message чтобы передать chat_id и user_id в start_quiz."""
    def __init__(self, chat_id, user_id):
        self.chat = type("C", (), {"id": chat_id})()
        self.from_user = type("U", (), {"id": user_id})()


def register(bot, ask_ai):  # noqa: F811  (переопределяем выше)
    """
    Финальная версия register — все хэндлеры в одном месте.
    Предыдущее определение выше — черновик, этот используется реально.
    """

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qz:topic:"))
    def on_topic(call):
        bot.answer_callback_query(call.id)
        topic = call.data[len("qz:topic:"):]
        show_count_menu(bot, call.message.chat.id, topic)

    @bot.callback_query_handler(func=lambda c: c.data == "qz:custom_topic")
    def on_custom_topic(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        _pending_topic[user_id] = True
        bot.send_message(
            call.message.chat.id,
            "✏️ Напиши свою тему для квиза:"
        )

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qz:count:"))
    def on_count(call):
        bot.answer_callback_query(call.id)
        parts = call.data[len("qz:count:"):].rsplit(":", 1)
        if len(parts) != 2:
            return
        topic, count_str = parts
        try:
            count = int(count_str)
        except ValueError:
            count = 5
        msg = _FakeMessage(call.message.chat.id, call.from_user.id)
        start_quiz(bot, ask_ai, msg, topic, count)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("quiz_ans:"))
    def on_answer(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        session = _quiz_sessions.get(user_id)
        if not session or session.get("answered"):
            return

        parts = call.data.split(":")
        if len(parts) != 3:
            return
        _, ans_i_str, q_i_str = parts
        ans_i = int(ans_i_str)
        q_i = int(q_i_str)

        if q_i != session["current_index"]:
            return

        q = session["questions"][q_i]
        correct_idx = q["correct_index"]
        correct_text = q["correct_text"]

        is_correct = (ans_i == correct_idx)
        if is_correct:
            session["correct_count"] += 1
        session["answered"] = True

        selected_text = q["options"][ans_i] if ans_i < len(q["options"]) else "?"
        if is_correct:
            feedback = f"✅ Твой ответ: {selected_text}\n\n✅ Верно!"
        else:
            feedback = (
                f"❌ Твой ответ: {selected_text}\n\n"
                f"✅ Правильный ответ: {correct_text}"
            )

        total = session["count"]
        i = session["current_index"]
        progress = _progress_bar(i, total)
        header = f"Вопрос {i + 1} из {total}\n{progress}"

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➡️ Далее", callback_data="quiz_next"))

        try:
            bot.edit_message_text(
                f"{header}\n\n{q['question']}\n\n{feedback}",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=kb,
            )
        except Exception:
            bot.send_message(chat_id, feedback, reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data == "quiz_next")
    def on_next(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        session = _quiz_sessions.get(user_id)
        if not session:
            return

        session["current_index"] += 1
        session["answered"] = False

        if session["current_index"] >= session["count"]:
            _finish_quiz(bot, chat_id, user_id)
        else:
            _send_question(bot, chat_id, user_id)

    @bot.callback_query_handler(func=lambda c: c.data == "menu:main")
    def on_menu_main(call):
        bot.answer_callback_query(call.id)
        user_id = call.from_user.id
        _quiz_sessions.pop(user_id, None)
        show_topic_menu(bot, call.message.chat.id)

    # ── Обработка текста для своей темы ─────────────────────────────────────

    @bot.message_handler(
        content_types=["text"],
        func=lambda m: _pending_topic.get(m.from_user.id)
    )
    def on_custom_topic_text(m):
        user_id = m.from_user.id
        if not _pending_topic.pop(user_id, False):
            return
        topic = m.text.strip()
        if not topic:
            bot.send_message(m.chat.id, "Тема не может быть пустой. Попробуй ещё раз.")
            return
        show_count_menu(bot, m.chat.id, topic)
