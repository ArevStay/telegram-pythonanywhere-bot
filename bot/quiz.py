import json
import random
from telebot import types

# Хранилище сессий квизов: {user_id: {topic, count, current_index, correct_count, questions}}
_quiz_sessions = {}

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (ОБЪЯВЛЕНЫ ПЕРВЫМИ)
# ==========================================

def generate_progress_bar(current, total):
    """Генерирует визуальную полоску прогресса"""
    length = 10
    filled = int(round((current / total) * length))
    return "🔹" * filled + "🔸" * (length - filled)


def send_question(bot, chat_id, user_id):
    """Отправляет текущий вопрос пользователю"""
    session = _quiz_sessions.get(user_id)
    if not session:
        return
        
    q_index = session["current_index"]
    current_q = session["questions"][q_index]
    
    progress = generate_progress_bar(q_index, session["count"])
    text = f"Вопрос {q_index + 1} из {session['count']}\nProgress: {progress}\n\n{current_q['question']}"
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    prefixes = ["A) ", "B) ", "C) "]
    
    for i, option in enumerate(current_q["options"]):
        prefix = prefixes[i] if i < len(prefixes) else ""
        kb.add(types.InlineKeyboardButton(f"{prefix}{option}", callback_data=f"quiz_ans:{i}:{q_index}"))
        
    bot.send_message(chat_id, text, reply_markup=kb)


def finish_quiz(bot, chat_id, user_id, session):
    """Завершает квиз и выводит результаты"""
    correct = session["correct_count"]
    total = session["count"]
    percent = int((correct / total) * 100) if total > 0 else 0
    
    text = (
        f"🎉 Квиз завершён!\n\n"
        f"🏆 Твой результат: {correct} из {total}\n"
        f"⭐ Ты набрал {percent}%\n\n"
        f"✅ Верных ответов: {correct}\n"
        f"❌ Неверных ответов: {total - correct}\n"
        f"📊 Всего вопросов: {total}\n\n"
    )
    
    if percent >= 80:
        text += f"🔥 Отличная работа! Ты настоящий знаток темы «{session['topic']}»! 💙"
    elif percent >= 50:
        text += "👍 Хороший результат! Можешь еще лучше!"
    else:
        text += "🙃 Стоит немного подтянуть знания по этой теме!"
        
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("🔄 Пройти ещё раз", callback_data=f"qz:topic:{session['topic']}"),
        types.InlineKeyboardButton("🏠 Главное меню", callback_data="menu:main")
    )
    
    bot.send_message(chat_id, text, reply_markup=kb)
    _quiz_sessions.pop(user_id, None)


def start_quiz(bot, ask_ai, message, topic: str, count: int):
    """Запускает квиз: запрашивает вопросы у AI, парсит JSON и отправляет первый вопрос."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    loading_msg = bot.send_message(chat_id, f"🔄 Генерирую квиз по теме «{topic}»...")
    
    prompt = (
        f"Сгенерируй викторину (квиз) на тему '{topic}'. "
        f"Количество вопросов: {count}. "
        f"Ответь СТРОГО в формате JSON массива объектов без какого-либо другого текста, разметки markdown или ```json. "
        f"Структура объекта: "
        f'{{"question": "текст вопроса", "options": ["вариант1", "вариант2", "вариант3"], "correct": "вариант1"}}. '
        f"Вариантов ответов должно быть ровно 3. Правильный ответ должен в точности совпадать с одним из вариантов в options."
    )
    
    try:
        ai_response = ask_ai(user_id, prompt)
        clean_json = ai_response.replace("```json", "").replace("```", "").strip()
        questions = json.loads(clean_json)
        
        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError("Неверный формат вопросов")
            
        questions = questions[:count]
        
        for q in questions:
            random.shuffle(q["options"])
            
        _quiz_sessions[user_id] = {
            "topic": topic,
            "count": len(questions),
            "current_index": 0,
            "correct_count": 0,
            "questions": questions
        }
        
        bot.delete_message(chat_id, loading_msg.message_id)
        send_question(bot, chat_id, user_id)
        
    except Exception as e:
        print(f"Quiz Error: {e}")
        bot.edit_message_text("❌ Не удалось создать квиз. Попробуйте другую тему.", chat_id=chat_id, message_id=loading_msg.message_id)


# ==========================================
# ОСНОВНОЙ МОДУЛЬ РЕГИСТРАЦИИ ХЭНДЛЕРОВ
# ==========================================

def register(bot, ask_ai):
    """Регистрирует хэндлеры для обработки ответов на квиз и перехода дальше."""
    
    @bot.callback_query_handler(func=lambda c: c.data.startswith("quiz_ans:"))
    def handle_answer(call):
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        session = _quiz_sessions.get(user_id)
        if not session:
            bot.send_message(chat_id, "Сессия квиза не найдена. Начните заново.")
            return
            
        _, ans_index, q_index = call.data.split(":")
        ans_index = int(ans_index)
        q_index = int(q_index)
        
        if q_index != session["current_index"]:
            return
            
        current_q = session["questions"][q_index]
        selected_text = current_q["options"][ans_index]
        correct_text = current_q["correct"]
        
        is_correct = (selected_text == correct_text)
        if is_correct:
            session["correct_count"] += 1
            feedback = "✅ Верно!"
        else:
            feedback = f"❌ Неверно! Правильный ответ: {correct_text}"
            
        text = (
            f"Вопрос {q_index + 1} из {session['count']}\n"
            f"Progress: {generate_progress_bar(q_index + 1, session['count'])}\n\n"
            f"{current_q['question']}\n\n"
            f"✅ Твой ответ: {selected_text}\n"
            f"{feedback}"
        )
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➡️ Далее", callback_data="quiz_next"))
        
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data == "quiz_next")
    def handle_next(call):
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        session = _quiz_sessions.get(user_id)
        if not session:
            return
            
        session["current_index"] += 1
        
        if session["current_index"] >= session["count"]:
            finish_quiz(bot, chat_id, user_id, session)
            return
            
        send_question(bot, chat_id, user_id)