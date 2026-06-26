"""
quest.py — Текстовый квест на базе AI.

Как работает:
  • /quest или кнопка «🗺️ Квест» запускает выбор жанра
  • AI генерирует сцены с описанием и вариантами выбора
  • Игрок нажимает на кнопку-вариант
  • AI продолжает историю исходя из выбора
  • Игра хранит историю до 10 шагов
  • Финал наступает после 8–10 ходов или по сюжету
"""

import json
from telebot import types

_quest_sessions = {}   # user_id -> session dict

QUEST_GENRES = [
    ("🏰 Фэнтези", "фэнтези: тёмные леса, замки, магия"),
    ("🚀 Космос", "космическая фантастика: звёздные корабли, инопланетяне"),
    ("🔍 Детектив", "детектив: загадочное убийство в особняке"),
    ("🧟 Хоррор", "хоррор: заброшенный дом с призраками"),
    ("⚔️ Самурай", "феодальная Япония: путь самурая"),
    ("🧙 К-поп звезда", "стань известным K-pop айдолом"),
]

MAX_STEPS = 10
FINISH_STEPS = 8   # после этого шага AI может завершить историю


class _FakeMessage:
    def __init__(self, chat_id, user_id):
        self.chat = type("C", (), {"id": chat_id})()
        self.from_user = type("U", (), {"id": user_id})()


# ─── Меню жанров ────────────────────────────────────────────────────────────

def show_genre_menu(bot, chat_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(label, callback_data=f"qst:genre:{genre}")
        for label, genre in QUEST_GENRES
    ]
    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="menu:main"))
    bot.send_message(
        chat_id,
        "🗺️ *Квест* — выбери жанр для своего приключения:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ─── Генерация первой сцены ─────────────────────────────────────────────────

def _build_start_prompt(genre: str) -> str:
    return (
        f"Ты — мастер текстовых квестов. Жанр: {genre}. "
        f"Начни захватывающую историю. "
        f"Опиши первую сцену (2–3 предложения) и дай ровно 3 варианта действия. "
        f"Верни ТОЛЬКО JSON без markdown:\n"
        f'{{"scene": "...", "choices": ["вариант 1", "вариант 2", "вариант 3"]}}\n'
        f"Сцена должна быть интригующей и атмосферной."
    )


def _build_continue_prompt(genre: str, history: list, choice: str, step: int) -> str:
    history_text = "\n".join(
        f"Шаг {i+1}: {h['scene'][:80]}... → {h['choice']}"
        for i, h in enumerate(history)
    )
    is_near_end = step >= FINISH_STEPS

    ending_hint = (
        " Это финал истории — завершения эпически, без вариантов выбора. "
        "Поле choices верни как []."
        if is_near_end
        else (
            f" Дай ровно 3 варианта действия. "
            f"Шаг {step} из {MAX_STEPS}."
        )
    )

    return (
        f"Жанр: {genre}. История до сих пор:\n{history_text}\n\n"
        f"Игрок выбрал: «{choice}».\n"
        f"Продолжи историю (2–3 предложения).{ending_hint}\n"
        f"Верни ТОЛЬКО JSON:\n"
        f'{{"scene": "...", "choices": [...]}}'
    )


# ─── Парсинг ответа AI ──────────────────────────────────────────────────────

def _parse_scene(raw: str):
    if not raw:
        return None
    try:
        cleaned = raw.strip()
        for fence in ("```json", "```"):
            if cleaned.startswith(fence):
                cleaned = cleaned[len(fence):]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        data = json.loads(cleaned)
        if isinstance(data, dict) and "scene" in data:
            return data
    except Exception:
        pass
    return None


# ─── Отправка сцены ─────────────────────────────────────────────────────────

def _send_scene(bot, chat_id, user_id):
    session = _quest_sessions.get(user_id)
    if not session:
        return

    step = session["step"]
    scene_data = session["current_scene"]
    scene_text = scene_data.get("scene", "...")
    choices = scene_data.get("choices", [])
    total = MAX_STEPS

    # Прогресс-бар
    filled = int((step / total) * 10)
    bar = "🟣" * filled + "⚫" * (10 - filled)
    header = f"🗺️ Квест | Шаг {step} из {total}\n{bar}"

    if not choices:
        # Финал
        text = f"{header}\n\n{scene_text}\n\n🏁 *Конец истории!*"
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("🔄 Играть снова", callback_data=f"qst:restart:{session['genre_label']}"),
            types.InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main"),
        )
        _quest_sessions.pop(user_id, None)
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    for idx, choice in enumerate(choices):
        kb.add(types.InlineKeyboardButton(
            choice, callback_data=f"qst:choice:{idx}"
        ))
    kb.add(types.InlineKeyboardButton("❌ Выйти из квеста", callback_data="menu:main"))

    text = f"{header}\n\n{scene_text}"
    bot.send_message(chat_id, text, reply_markup=kb)


# ─── Запуск квеста ──────────────────────────────────────────────────────────

def start_quest(bot, ask_ai, chat_id, user_id, genre: str, genre_label: str):
    loading = bot.send_message(chat_id, "⏳ Создаю твоё приключение...")

    try:
        prompt = _build_start_prompt(genre)
        # Используем ask_ai с нейтральным user_id чтобы не засорять историю чата
        raw = ask_ai(user_id, prompt)
        scene_data = _parse_scene(raw)

        if not scene_data:
            scene_data = {
                "scene": f"Ты оказался в мире «{genre}». Вокруг загадочная тишина...",
                "choices": ["Идти вперёд", "Осмотреться", "Вернуться назад"],
            }

        _quest_sessions[user_id] = {
            "genre": genre,
            "genre_label": genre_label,
            "step": 1,
            "history": [],
            "current_scene": scene_data,
        }

        try:
            bot.delete_message(chat_id, loading.message_id)
        except Exception:
            pass

        _send_scene(bot, chat_id, user_id)

    except Exception:
        try:
            bot.edit_message_text(
                "❌ Не удалось создать квест. Попробуй ещё раз.",
                chat_id=chat_id,
                message_id=loading.message_id,
            )
        except Exception:
            pass


# ─── Регистрация хэндлеров ──────────────────────────────────────────────────

def register(bot, ask_ai):

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qst:genre:"))
    def on_genre(call):
        bot.answer_callback_query(call.id)
        genre = call.data[len("qst:genre:"):]
        # Находим метку жанра
        genre_label = genre
        for label, g in QUEST_GENRES:
            if g == genre:
                genre_label = label
                break
        start_quest(
            bot, ask_ai,
            call.message.chat.id, call.from_user.id,
            genre, genre_label,
        )

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qst:choice:"))
    def on_choice(call):
        bot.answer_callback_query(call.id)

        user_id = call.from_user.id
        chat_id = call.message.chat.id

        session = _quest_sessions.get(user_id)
        if not session:
            bot.send_message(chat_id, "Квест не найден. Начни заново: /quest")
            return

        idx_str = call.data[len("qst:choice:"):]
        try:
            idx = int(idx_str)
        except ValueError:
            return

        choices = session["current_scene"].get("choices", [])
        if idx >= len(choices):
            return

        chosen = choices[idx]
        step = session["step"]

        # Сохраняем историю
        session["history"].append({
            "scene": session["current_scene"]["scene"],
            "choice": chosen,
        })
        session["step"] += 1

        loading = bot.send_message(chat_id, "⏳ Продолжаю историю...")

        try:
            prompt = _build_continue_prompt(
                session["genre"],
                session["history"],
                chosen,
                session["step"],
            )
            raw = ask_ai(user_id, prompt)
            scene_data = _parse_scene(raw)

            if not scene_data:
                scene_data = {
                    "scene": "История продолжается...",
                    "choices": (
                        ["Идти дальше", "Осмотреться", "Подождать"]
                        if session["step"] < FINISH_STEPS
                        else []
                    ),
                }

            session["current_scene"] = scene_data

            try:
                bot.delete_message(chat_id, loading.message_id)
            except Exception:
                pass

            _send_scene(bot, chat_id, user_id)

        except Exception:
            try:
                bot.edit_message_text(
                    "❌ Ошибка. Попробуй ещё раз.",
                    chat_id=chat_id,
                    message_id=loading.message_id,
                )
            except Exception:
                pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith("qst:restart:"))
    def on_restart(call):
        bot.answer_callback_query(call.id)
        genre_label = call.data[len("qst:restart:"):]
        # Ищем genre по label
        for label, genre in QUEST_GENRES:
            if label == genre_label:
                start_quest(
                    bot, ask_ai,
                    call.message.chat.id, call.from_user.id,
                    genre, label,
                )
                return
        show_genre_menu(bot, call.message.chat.id)
