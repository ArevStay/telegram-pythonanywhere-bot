import os
from datetime import datetime

from telebot import types

from bot.quiz import register as register_quiz, start_quiz
from bot.clients import bot, BOT_INFO, store
from bot.config import HF_SPACE_ID
from bot.ai import ask_ai
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.rate_limit import is_rate_limited


VERBOSE_LOG = os.environ.get("BOT_VERBOSE_LOG", "").strip().lower() in (
    "1", "true", "yes", "on"
)

# =========================
# QUIZ STATE (НОВОЕ)
# =========================

_QUIZ_STATE = {}

QUICK_QUIZ_TOPICS = ["Космос", "Python", "История", "Кино"]

# =========================
# BUTTONS
# =========================

BTN_QUEST = "🎮 AI Квест"
BTN_QUIZ = "🧠 Квиз"
BTN_JOKE = "😂 Шутка"
BTN_FACT = "💡 Факт"
BTN_COMPLIMENT = "😊 Комплимент"

BTN_REMEMBER = "💾 Заметка"
BTN_RECALL = "📖 Вспомнить"
BTN_FORGET = "🗑️ Забыть"

BTN_RESET = "🔄 Сброс диалога"
BTN_ABOUT = "ℹ️ О боте"
BTN_HELP = "❓ Помощь"
BTN_MODEL = "⚙️ Модель"

BTN_MAIN_MENU = "🏠 Главное меню"


# =========================
# KEYBOARDS
# =========================

def main_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)

    kb.row(
        types.InlineKeyboardButton(BTN_QUIZ, callback_data="menu:quiz"),
        types.InlineKeyboardButton(BTN_QUEST, callback_data="menu:quest"),
    )
    kb.row(
        types.InlineKeyboardButton(BTN_JOKE, callback_data="menu:joke"),
        types.InlineKeyboardButton(BTN_FACT, callback_data="menu:fact"),
        types.InlineKeyboardButton(BTN_COMPLIMENT, callback_data="menu:compliment"),
    )
    kb.row(
        types.InlineKeyboardButton(BTN_REMEMBER, callback_data="menu:remember"),
        types.InlineKeyboardButton(BTN_RECALL, callback_data="menu:recall"),
        types.InlineKeyboardButton(BTN_FORGET, callback_data="menu:forget"),
    )
    kb.row(
        types.InlineKeyboardButton(BTN_RESET, callback_data="menu:reset"),
        types.InlineKeyboardButton(BTN_ABOUT, callback_data="menu:about"),
        types.InlineKeyboardButton(BTN_HELP, callback_data="menu:help"),
    )

    if HF_SPACE_ID:
        kb.row(types.InlineKeyboardButton(BTN_MODEL, callback_data="menu:model"))

    return kb


def quiz_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("5", callback_data="qz:num:5"),
        types.InlineKeyboardButton("7", callback_data="qz:num:7"),
        types.InlineKeyboardButton("10", callback_data="qz:num:10"),
    )
    kb.add(types.InlineKeyboardButton("✏️ Своя тема", callback_data="qz:num:custom"))
    return kb


def quiz_topics_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)

    for t in QUICK_QUIZ_TOPICS:
        kb.add(types.InlineKeyboardButton(t, callback_data=f"qz:topic:{t}"))

    kb.row(types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"))
    return kb


def back_to_menu_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"))
    return kb


def again_keyboard(action: str):
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🔄 Ещё", callback_data=f"menu:{action}"),
        types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"),
    )
    return kb


# =========================
# CALLBACK SHIM
# =========================

class _CallbackMessage:
    def __init__(self, call):
        self.chat = call.message.chat
        self.from_user = call.from_user
        self.text = ""


# =========================
# LOGGING
# =========================

def _log(message, direction: str, text: str):
    if not VERBOSE_LOG:
        return

    user = message.from_user
    name = f"@{user.username}" if user.username else user.first_name

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {name}: {text}")


# =========================
# MEMORY
# =========================

_MEMORY_NOTES = {}

def _save_note(user_id, text):
    if store:
        store.set(f"note:{user_id}", text)
    else:
        _MEMORY_NOTES[user_id] = text


def _get_note(user_id):
    return store.get(f"note:{user_id}") if store else _MEMORY_NOTES.get(user_id)


def _delete_note(user_id):
    if store:
        store.delete(f"note:{user_id}")
    else:
        _MEMORY_NOTES.pop(user_id, None)


# =========================
# ACTIONS
# =========================

def _send_joke(chat_id, user_id):
    r = ask_ai(user_id, "Расскажи короткую шутку")
    bot.send_message(chat_id, f"😂 {r}", reply_markup=again_keyboard("joke"))


def _send_fact(chat_id, user_id):
    r = ask_ai(user_id, "Интересный факт о программировании")
    bot.send_message(chat_id, f"💡 {r}", reply_markup=again_keyboard("fact"))


def _send_compliment(chat_id, user_id):
    r = ask_ai(user_id, "Комплимент пользователю")
    bot.send_message(chat_id, f"😊 {r}", reply_markup=again_keyboard("compliment"))


def _do_remember(message):
    text = (message.text or "").strip()

    if not text:
        bot.send_message(message.chat.id, "Пусто")
        return

    _save_note(message.from_user.id, text)
    bot.send_message(message.chat.id, "💾 Сохранено", reply_markup=back_to_menu_keyboard())


# =========================
# COMMANDS
# =========================

@bot.message_handler(commands=["start"], func=is_allowed)
def start(m):
    bot.send_message(m.chat.id, "👋 Привет!", reply_markup=main_menu_keyboard())


@bot.message_handler(commands=["help"], func=is_allowed)
def help_cmd(m):
    bot.send_message(m.chat.id, "/start /quiz /joke /fact /reset")


@bot.message_handler(commands=["joke"], func=is_allowed)
def joke(m):
    _send_joke(m.chat.id, m.from_user.id)


@bot.message_handler(commands=["fact"], func=is_allowed)
def fact(m):
    _send_fact(m.chat.id, m.from_user.id)


@bot.message_handler(commands=["compliment"], func=is_allowed)
def comp(m):
    _send_compliment(m.chat.id, m.from_user.id)


@bot.message_handler(commands=["reset"], func=is_allowed)
def reset(m):
    clear_history(m.from_user.id)
    bot.send_message(m.chat.id, "очищено")


@bot.message_handler(commands=["remember"], func=is_allowed)
def remember(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        return
    _save_note(m.from_user.id, parts[1])
    bot.send_message(m.chat.id, "saved")


@bot.message_handler(commands=["recall"], func=is_allowed)
def recall(m):
    bot.send_message(m.chat.id, _get_note(m.from_user.id) or "empty")


@bot.message_handler(commands=["forget"], func=is_allowed)
def forget(m):
    _delete_note(m.from_user.id)
    bot.send_message(m.chat.id, "deleted")


# =========================
# MENU CALLBACK
# =========================

@bot.callback_query_handler(func=lambda c: c.data.startswith("menu:"))
def menu(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)

    action = call.data.split(":")[1]

    if action == "quiz":
        bot.send_message(chat_id, "Выбери количество вопросов:", reply_markup=quiz_keyboard())

    elif action == "main":
        bot.send_message(chat_id, "🏠 меню", reply_markup=main_menu_keyboard())

    elif action == "joke":
        _send_joke(chat_id, user_id)

    elif action == "fact":
        _send_fact(chat_id, user_id)

    elif action == "compliment":
        _send_compliment(chat_id, user_id)

    elif action == "remember":
        msg = bot.send_message(chat_id, "напиши заметку")
        bot.register_next_step_handler(msg, _do_remember)

    elif action == "recall":
        bot.send_message(chat_id, _get_note(user_id) or "нет заметки")

    elif action == "forget":
        _delete_note(user_id)
        bot.send_message(chat_id, "удалено")

    elif action == "reset":
        clear_history(user_id)
        bot.send_message(chat_id, "очищено")

    elif action == "about":
        bot.send_message(chat_id, "бот")

    elif action == "help":
        help_cmd(_CallbackMessage(call))


## =========================
# QUIZ FIX (ОБНОВЛЕННЫЙ)
# =========================

_QUIZ_STATE = {}

@bot.callback_query_handler(func=lambda c: c.data.startswith("qz:num:"))
def quiz_num(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    value = call.data.split(":")[2]

    # Своя тема
    if value == "custom":
        msg = bot.send_message(chat_id, "✏️ Введите свою тему для квиза:")
        
        # Фиксируем дефолтное количество вопросов (например, 5) для кастомной темы
        _QUIZ_STATE[user_id] = 5 
        
        def handle_custom(m):
            count = _QUIZ_STATE.get(m.from_user.id, 5)
            start_quiz(bot, ask_ai, m, m.text, count)
            _QUIZ_STATE.pop(m.from_user.id, None)

        bot.register_next_step_handler(msg, handle_custom)
        return

    # Сохраняем выбранное количество вопросов
    try:
        _QUIZ_STATE[user_id] = int(value)
    except Exception:
        _QUIZ_STATE[user_id] = 5

    # Предлагаем клавиатуру с быстрыми топиками (Космос, Python, Stray Kids и т.д.)
    bot.send_message(
        chat_id,
        "🎯 Выбери тему для квиза:",
        reply_markup=quiz_topics_keyboard()
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("qz:topic:"))
def quiz_topic(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    topic = call.data.split(":", 2)[2]

    # Извлекаем сохраненное ранее число вопросов
    count = _QUIZ_STATE.get(user_id, 5)

    # Запускаем движок квиза
    start_quiz(
        bot,
        ask_ai,
        _CallbackMessage(call),
        topic,
        count
    )

    # Очищаем промежуточное состояние выбора количества вопросов
    _QUIZ_STATE.pop(user_id, None)

# =========================
# QUIZ MODULE
# =========================

register_quiz(bot, ask_ai)


# =========================
# AI CHAT
# =========================

@bot.message_handler(content_types=["text"], func=is_allowed)
def chat(m):
    if not should_respond(m):
        return

    try:
        with keep_typing(m.chat.id):
            r = ask_ai(m.from_user.id, m.text)

        send_reply(m, r)

    except Exception as e:
        print(e)
        bot.send_message(m.chat.id, "error")