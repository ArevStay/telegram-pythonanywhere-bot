import os
from datetime import datetime

from telebot import types

from bot.quiz import register as register_quiz, start_quiz
from bot.clients import bot, BOT_INFO, store
from bot.config import COMMIT_SHA, HF_SPACE_ID, HOSTING_LABEL, MODEL, RATE_LIMIT
from bot.ai import ask_ai
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.preferences import get_provider, set_provider
from bot.rate_limit import is_rate_limited


# Verbose logging
VERBOSE_LOG = os.environ.get("BOT_VERBOSE_LOG", "").strip().lower() in (
    "1", "true", "yes", "on"
)

# =========================
# MENU — labels (also used as the displayed text on inline buttons)
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

QUICK_QUIZ_TOPICS = ["Космос", "Python", "История", "Кино"]


# =========================
# INLINE KEYBOARDS
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
    row3 = [
        types.InlineKeyboardButton(BTN_RESET, callback_data="menu:reset"),
        types.InlineKeyboardButton(BTN_ABOUT, callback_data="menu:about"),
        types.InlineKeyboardButton(BTN_HELP, callback_data="menu:help"),
    ]
    kb.row(*row3)
    if HF_SPACE_ID:
        kb.row(types.InlineKeyboardButton(BTN_MODEL, callback_data="menu:model"))
    return kb


def back_to_menu_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"))
    return kb


def again_keyboard(action: str):
    """Keyboard with a 'do it again' button plus a way back to the menu.

    Used under jokes/facts/compliments so the person can keep tapping
    without retyping a command.
    """
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("🔄 Ещё", callback_data=f"menu:{action}"),
        types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"),
    )
    return kb


def quiz_topics_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(*[
        types.InlineKeyboardButton(t, callback_data=f"qz:{t}")
        for t in QUICK_QUIZ_TOPICS
    ])
    kb.row(types.InlineKeyboardButton("✏️ Своя тема", callback_data="qz:custom"))
    kb.row(types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"))
    return kb


def model_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("⚡ Main", callback_data="model:main"),
        types.InlineKeyboardButton("🇦🇲 HF (Armenian)", callback_data="model:hf"),
    )
    kb.row(types.InlineKeyboardButton(BTN_MAIN_MENU, callback_data="menu:main"))
    return kb


class _CallbackMessage:
    """Minimal Message-shaped shim built from a CallbackQuery.

    Lets command handlers written for `message.chat` / `message.from_user`
    be reused when the same action is triggered by tapping an inline
    button instead of typing a command. `call.message` is the bot's own
    message (so its `from_user` would be the bot) — we want the chat from
    that, but the *person* who tapped the button.
    """

    def __init__(self, call):
        self.chat = call.message.chat
        self.from_user = call.from_user
        self.text = ""


def _log(message, direction: str, text: str) -> None:
    if not VERBOSE_LOG:
        return

    user = message.from_user
    user_name = f"@{user.username}" if user.username else (user.first_name or f"user:{user.id}")
    bot_name = f"@{BOT_INFO.username}"

    snippet = (text or "").replace("\n", " ").replace("\r", " ")
    if len(snippet) > 500:
        snippet = snippet[:500] + "..."

    sender, receiver = (user_name, bot_name) if direction == "in" else (bot_name, user_name)

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {sender} → {receiver}: {snippet}", flush=True)


# =========================
# NOTES STORAGE (remember/recall)
# =========================

_MEMORY_NOTES = {}

def _save_note(user_id: int, text: str) -> None:
    if store is not None:
        store.set(f"note:{user_id}", text)
    else:
        _MEMORY_NOTES[user_id] = text


def _get_note(user_id: int):
    if store is not None:
        return store.get(f"note:{user_id}")
    return _MEMORY_NOTES.get(user_id)


def _delete_note(user_id: int) -> None:
    if store is not None:
        store.delete(f"note:{user_id}")
    else:
        _MEMORY_NOTES.pop(user_id, None)


# =========================
# SHARED ACTION LOGIC (used by both /commands and inline buttons)
# =========================

def _send_joke(chat_id, user_id):
    reply = ask_ai(user_id, "Расскажи одну короткую остроумную шутку.")
    bot.send_message(chat_id, f"😂 {reply}", reply_markup=again_keyboard("joke"))


def _send_fact(chat_id, user_id):
    reply = ask_ai(user_id, "Расскажи один интересный факт о программировании.")
    bot.send_message(chat_id, f"💡 {reply}", reply_markup=again_keyboard("fact"))


def _send_compliment(chat_id, user_id):
    reply = ask_ai(user_id, "Сделай один приятный, искренний комплимент.")
    bot.send_message(chat_id, f"😊 {reply}", reply_markup=again_keyboard("compliment"))


def _do_remember(message):
    text = (message.text or "").strip()
    if not text:
        bot.send_message(message.chat.id, "Пустая заметка — отменено.", reply_markup=back_to_menu_keyboard())
        return
    _save_note(message.from_user.id, text)
    bot.send_message(message.chat.id, "💾 Заметка сохранена!", reply_markup=back_to_menu_keyboard())


# =========================
# COMMANDS
# =========================

@bot.message_handler(commands=["roast"], func=is_allowed)
def cmd_roast(message):
    name = message.text.split(maxsplit=1)[1] if " " in message.text else "тебя"
    reply = ask_ai(message.from_user.id, f"Напиши короткую но смешную шутку про {name}.")
    bot.send_message(message.chat.id, reply, reply_markup=back_to_menu_keyboard())


@bot.message_handler(commands=["start"], func=is_allowed)
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет!\n\n"
        "Я ИИ помощник. Выбери действие на кнопках ниже "
        "или просто напиши мне что-нибудь.",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(commands=["help"], func=is_allowed)
def cmd_help(message):
    lines = [
        "/start — приветствие и главное меню",
        "/help  — это сообщение",
        "/reset — очистить историю диалога",
        "/about — о боте",
        "/joke  — короткая шутка",
        "/fact  — интересный факт о программировании",
        "/compliment — комплимент",
        "/roast <имя> — шутка про кого-то",
        "/remember <текст> — сохранить заметку",
        "/recall — показать заметку",
        "/forget — удалить заметку",
        "/quiz <тема> — начать квиз по теме",
    ]
    if HF_SPACE_ID:
        lines.append("/model — переключить ИИ-модель")
    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=back_to_menu_keyboard())


@bot.message_handler(commands=["joke"], func=is_allowed)
def cmd_joke(message):
    _send_joke(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["fact"], func=is_allowed)
def cmd_fact(message):
    _send_fact(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["compliment"], func=is_allowed)
def cmd_compliment(message):
    _send_compliment(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["reset"], func=is_allowed)
def cmd_clear(message):
    clear_history(message.from_user.id)
    bot.send_message(message.chat.id, "🔄 История диалога очищена.", reply_markup=back_to_menu_keyboard())


@bot.message_handler(commands=["about"], func=is_allowed)
def cmd_about(message):
    if HF_SPACE_ID:
        provider = get_provider(message.from_user.id)
        model_line = f"{MODEL} (main)" if provider == "main" else f"{HF_SPACE_ID} (hf)"
    else:
        model_line = MODEL

    storage_line = "SQLite" if store is not None else "stateless (no memory)"

    lines = [
        f"Model  : {model_line}",
        f"Storage: {storage_line}",
        f"Hosting: {HOSTING_LABEL}",
    ]

    if COMMIT_SHA:
        lines.append(f"Version: {COMMIT_SHA}")

    bot.send_message(message.chat.id, "\n".join(lines), reply_markup=back_to_menu_keyboard())


# =========================
# MEMORY COMMANDS
# =========================

@bot.message_handler(commands=["remember"], func=is_allowed)
def cmd_remember(message):
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /remember <your note>")
        return

    note = parts[1].strip()
    _save_note(message.from_user.id, note)

    bot.send_message(message.chat.id, "💾 Saved!", reply_markup=back_to_menu_keyboard())


@bot.message_handler(commands=["recall"], func=is_allowed)
def cmd_recall(message):
    note = _get_note(message.from_user.id)

    if not note:
        bot.send_message(message.chat.id, "No saved note yet.", reply_markup=back_to_menu_keyboard())
        return

    bot.send_message(message.chat.id, f"🧠 Your note:\n{note}", reply_markup=back_to_menu_keyboard())


@bot.message_handler(commands=["forget"], func=is_allowed)
def cmd_forget(message):
    _delete_note(message.from_user.id)
    bot.send_message(message.chat.id, "🗑️ Deleted saved note.", reply_markup=back_to_menu_keyboard())


# =========================
# OPTIONAL MODEL SWITCH
# =========================

if HF_SPACE_ID:

    @bot.message_handler(commands=["model"], func=is_allowed)
    def cmd_model(message):
        parts = (message.text or "").split(maxsplit=1)

        if len(parts) == 1:
            current = get_provider(message.from_user.id)
            bot.send_message(
                message.chat.id,
                f"Current provider: {current}\n\n"
                "/model main — fast multilingual\n"
                "/model hf — Armenian-only model",
                reply_markup=model_keyboard(),
            )
            return

        choice = parts[1].strip().lower()

        if choice not in ("main", "hf"):
            bot.send_message(message.chat.id, "❌ Invalid choice. Use: /model main or /model hf")
            return

        if not set_provider(message.from_user.id, choice):
            bot.send_message(message.chat.id, "⚠️ Could not save preference.")
            return

        if choice == "hf":
            bot.send_message(
                message.chat.id,
                "✅ Switched to hf — Armenian-only model.",
                reply_markup=back_to_menu_keyboard(),
            )
        else:
            bot.send_message(
                message.chat.id,
                "✅ Switched to Main — fast multilingual model.",
                reply_markup=back_to_menu_keyboard(),
            )

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("model:"))
    def model_callback(call):
        choice = call.data.split(":", 1)[1]
        bot.answer_callback_query(call.id)
        chat_id = call.message.chat.id
        user_id = call.from_user.id

        if not set_provider(user_id, choice):
            bot.send_message(chat_id, "⚠️ Could not save preference.")
            return

        if choice == "hf":
            bot.send_message(
                chat_id,
                "✅ Switched to hf — Armenian-only model.",
                reply_markup=back_to_menu_keyboard(),
            )
        else:
            bot.send_message(
                chat_id,
                "✅ Switched to Main — fast multilingual model.",
                reply_markup=back_to_menu_keyboard(),
            )


# =========================
# INLINE MENU CALLBACKS
# =========================

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("menu:"))
def menu_callback(call):
    action = call.data.split(":", 1)[1]
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)

    if action == "main":
        bot.send_message(chat_id, "🏠 <b>Главное меню</b>", parse_mode="HTML", reply_markup=main_menu_keyboard())
    elif action == "quiz":
        bot.send_message(chat_id, "🧠 Выбери тему квиза или предложи свою:", reply_markup=quiz_topics_keyboard())
    elif action == "quest":
        bot.send_message(chat_id, "🎮 AI Квест пока не реализован.", reply_markup=back_to_menu_keyboard())
    elif action == "joke":
        _send_joke(chat_id, user_id)
    elif action == "fact":
        _send_fact(chat_id, user_id)
    elif action == "compliment":
        _send_compliment(chat_id, user_id)
    elif action == "remember":
        sent = bot.send_message(chat_id, "✏️ Напиши текст заметки:")
        bot.register_next_step_handler(sent, _do_remember)
    elif action == "recall":
        note = _get_note(user_id)
        text = f"🧠 Твоя заметка:\n{note}" if note else "У тебя пока нет сохранённой заметки."
        bot.send_message(chat_id, text, reply_markup=back_to_menu_keyboard())
    elif action == "forget":
        _delete_note(user_id)
        bot.send_message(chat_id, "🗑️ Заметка удалена.", reply_markup=back_to_menu_keyboard())
    elif action == "reset":
        clear_history(user_id)
        bot.send_message(chat_id, "🔄 История диалога очищена.", reply_markup=back_to_menu_keyboard())
    elif action == "about":
        cmd_about(_CallbackMessage(call))
    elif action == "help":
        cmd_help(_CallbackMessage(call))
    elif action == "model" and HF_SPACE_ID:
        current = get_provider(user_id)
        bot.send_message(chat_id, f"Текущая модель: {current}", reply_markup=model_keyboard())


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("qz:"))
def quiz_topic_callback(call):
    topic = call.data.split(":", 1)[1]
    bot.answer_callback_query(call.id)

    if topic == "custom":
        sent = bot.send_message(call.message.chat.id, "✏️ Напиши тему квиза:")
        bot.register_next_step_handler(sent, lambda m: start_quiz(bot, ask_ai, m, m.text))
        return

    start_quiz(bot, ask_ai, _CallbackMessage(call), topic)


# =========================
# MAIN MESSAGE HANDLER
# =========================

@bot.message_handler(content_types=["text"], func=is_allowed)
def handle_message(message):
    if not should_respond(message):
        return

    text = (message.text or "").replace(f"@{BOT_INFO.username}", "").strip()
    if not text:
        return

    _log(message, "in", text)

    if is_rate_limited(message.from_user.id):
        msg = f"You've reached the daily limit of {RATE_LIMIT} messages."
        bot.send_message(message.chat.id, msg)
        _log(message, "out", msg)
        return

    try:
        with keep_typing(message.chat.id):
            reply = ask_ai(message.from_user.id, text)

        send_reply(message, reply)
        _log(message, "out", reply)

    except Exception as e:
        print(f"Error: {e}")
        bot.send_message(message.chat.id, "Something went wrong. Try again.")
        _log(message, "out", f"[error] {e}")


# Wire up /quiz command + in-quiz answer-button callbacks from bot/quiz.py.
# (Previously imported but never called — the quiz command and its inline
# answer buttons silently did nothing.)
register_quiz(bot, ask_ai)
