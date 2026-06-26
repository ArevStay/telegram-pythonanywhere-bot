import os
import random
from datetime import datetime



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
# MENU
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

BTN_MAIN_MENU = "🏠 Главное меню"


def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    kb.row(BTN_QUEST, BTN_QUIZ)
    kb.row(BTN_JOKE, BTN_FACT, BTN_COMPLIMENT)
    kb.row(BTN_REMEMBER, BTN_RECALL, BTN_FORGET)
    kb.row(BTN_RESET, BTN_ABOUT, BTN_HELP)
    kb.row(BTN_MAIN_MENU)

    return kb

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
# COMMANDS
# =========================

@bot.message_handler(commands=["roast"], func=is_allowed)
def cmd_roast(message):
    name = message.text.split(maxsplit=1)[1] if " " in message.text else "you"
    reply = ask_ai(message.from_user.id, f"Напиши короткую но смешную шутку про {name}.")
    bot.send_message(message.chat.id, reply)



@bot.message_handler(commands=["start"], func=is_allowed)
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет!\n\n"
        "Я ИИ помощник.\n"
        "Используй кнопки меню ниже или просто отправь сообщение.",
        reply_markup=main_menu_keyboard(),
    )

# =========================
# MENU BUTTONS
# =========================

@bot.message_handler(func=lambda m: m.text == BTN_JOKE)
def menu_joke(message):
    cmd_joke(message)


@bot.message_handler(func=lambda m: m.text == BTN_FACT)
def menu_fact(message):
    cmd_fact(message)


@bot.message_handler(func=lambda m: m.text == BTN_COMPLIMENT)
def menu_compliment(message):
    cmd_compliment(message)


@bot.message_handler(func=lambda m: m.text == BTN_RECALL)
def menu_recall(message):
    cmd_recall(message)


@bot.message_handler(func=lambda m: m.text == BTN_FORGET)
def menu_forget(message):
    cmd_forget(message)


@bot.message_handler(func=lambda m: m.text == BTN_RESET)
def menu_reset(message):
    cmd_clear(message)


@bot.message_handler(func=lambda m: m.text == BTN_ABOUT)
def menu_about(message):
    cmd_about(message)


@bot.message_handler(func=lambda m: m.text == BTN_HELP)
def menu_help(message):
    cmd_help(message)


@bot.message_handler(func=lambda m: m.text == BTN_MAIN_MENU)
def menu_main(message):
    bot.send_message(
        message.chat.id,
        "🏠 Главное меню",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == BTN_REMEMBER)
def menu_remember(message):
    bot.send_message(
        message.chat.id,
        "Напишите:\n/remember ваш текст",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == BTN_QUEST)
def menu_quest(message):
    bot.send_message(
        message.chat.id,
        "🎮 AI Квест пока не реализован.",
        reply_markup=main_menu_keyboard(),
    )


@bot.message_handler(func=lambda m: m.text == BTN_QUIZ)
def menu_quiz(message):
    bot.send_message(
        
        message.chat.id,
        "🧠 Квиз пока не реализован.",
        reply_markup=main_menu_keyboard(),
        
    )


@bot.message_handler(commands=["help"], func=is_allowed)
def cmd_help(message):
    lines = [
        "/start — welcome message",
        "/help  — show this message",
        "/reset — clear conversation history",
        "/about — about this bot",
        "/joke  — get a random programming joke",
        "/fact  — get a random programming fact",
        "/compliment — get a nice compliment",
        "/roast <name> — roast someone",
        "/remember <note> — save a note",
        "/recall — show saved note",
        "/forget — delete saved note",
    ]
    bot.send_message(message.chat.id, "\n".join(lines))


@bot.message_handler(commands=["joke"], func=is_allowed)
def cmd_joke(message):
    reply_markup=main_menu_keyboard()
    reply = ask_ai(message.from_user.id, "Расскажи одну короткую шутку.")
    bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=["fact"], func=is_allowed)
def cmd_fact(message):
    reply_markup=main_menu_keyboard()
    reply = ask_ai(message.from_user.id, "Расскажи один интересный факт о программировании.")
    bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=["reset"], func=is_allowed)
def cmd_clear(message):
    reply_markup=main_menu_keyboard()
    clear_history(message.from_user.id)
    bot.send_message(message.chat.id, "Conversation history cleared.")


@bot.message_handler(commands=["about"], func=is_allowed)
def cmd_about(message):
    reply_markup=main_menu_keyboard()
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

    bot.send_message(message.chat.id, "\n".join(lines))


# =========================
# MEMORY COMMANDS
# =========================

@bot.message_handler(commands=["remember"], func=is_allowed)
def cmd_remember(message):
    reply_markup=main_menu_keyboard()
    parts = (message.text or "").split(maxsplit=1)

    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /remember <your note>")
        return

    note = parts[1].strip()
    _save_note(message.from_user.id, note)

    bot.send_message(message.chat.id, "💾 Saved!")


@bot.message_handler(commands=["recall"], func=is_allowed)
def cmd_recall(message):
    reply_markup=main_menu_keyboard()
    note = _get_note(message.from_user.id)

    if not note:
        bot.send_message(message.chat.id, "No saved note yet.")
        return

    bot.send_message(message.chat.id, f"🧠 Your note:\n{note}")


@bot.message_handler(commands=["forget"], func=is_allowed)
def cmd_forget(message):
    reply_markup=main_menu_keyboard()
    _delete_note(message.from_user.id)
    bot.send_message(message.chat.id, "🗑️ Deleted saved note.")


# =========================
# OPTIONAL MODEL SWITCH
# =========================

if HF_SPACE_ID:

    @bot.message_handler(commands=["model"], func=is_allowed)
    def cmd_model(message):
        reply_markup=main_menu_keyboard()
        parts = (message.text or "").split(maxsplit=1)

        if len(parts) == 1:
            current = get_provider(message.from_user.id)
            bot.send_message(
                message.chat.id,
                f"Current provider: {current}\n\n"
                "/model main — fast multilingual\n"
                "/model hf — Armenian-only model",
            )
            return

        choice = parts[1].strip().lower()

        if choice not in ("main", "hf"):
            bot.send_message(message.chat.id, "Use: /model main or /model hf")
            return

        if not set_provider(message.from_user.id, choice):
            bot.send_message(message.chat.id, "Could not save preference.")
            return

        bot.send_message(message.chat.id, f"Switched to {choice}")


# =========================
# MAIN MESSAGE HANDLER
# =========================

@bot.message_handler(content_types=["text"], func=is_allowed)
def handle_message(message):
    reply_markup=main_menu_keyboard()
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


@bot.message_handler(commands=["compliment"], func=is_allowed)
def cmd_compliment(message):
    reply_markup=main_menu_keyboard()
    reply = ask_ai(message.from_user.id, "Give a nice compliment.")
    bot.send_message(message.chat.id, reply)