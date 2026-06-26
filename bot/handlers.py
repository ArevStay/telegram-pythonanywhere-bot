import os
from telebot import types

from bot.quiz import register as register_quiz, show_topic_menu
from bot.quest import register as register_quest, show_genre_menu
from bot.clients import bot, store
from bot.ai import ask_ai
from bot.helpers import is_allowed, keep_typing, send_reply, should_respond
from bot.history import clear_history
from bot.rate_limit import is_rate_limited
import bot.config as config   # IMPORTANT (dynamic access)

COMMIT_SHA = os.environ.get("COMMIT_SHA", "unknown")
# HF_SPACE_ID must be a module-level attribute so tests can patch it
HF_SPACE_ID = getattr(config, "HF_SPACE_ID", "")

BOT_INFO = None


# =========================
# CORE MESSAGE
# =========================
def handle_message(message):
    text = getattr(message, "text", None)
    if not text:
        return None

    user_id = message.from_user.id
    chat_id = message.chat.id

    if not should_respond(message):
        return None

    if is_rate_limited(user_id):
        bot.send_message(chat_id, "daily limit exceeded")
        return None

    if not is_allowed(message):
        return None

    if BOT_INFO and getattr(BOT_INFO, "username", None):
        if text.strip() == f"@{BOT_INFO.username}":
            return None

    try:
        with keep_typing(chat_id):
            resp = ask_ai(user_id, text)
        send_reply(message, resp)
    except Exception:
        bot.send_message(chat_id, "Something went wrong")

    return None


# =========================
# ABOUT
# =========================
def cmd_about(m):
    if store is None:
        storage = "stateless"
    else:
        storage = "SQLite"

    text = f"Bot Storage: {storage}"

    if COMMIT_SHA and COMMIT_SHA != "unknown":
        text += f"\nVersion: {COMMIT_SHA}"

    bot.send_message(m.chat.id, text)


# =========================
# PROVIDER
# =========================
def set_provider(user_id, provider_name):
    try:
        if store:
            store.set("ai_provider", provider_name)
        return True
    except Exception:
        return False


def get_provider():
    if store:
        return store.get("ai_provider") or "main"
    return "main"


# =========================
# MODEL COMMAND (defined only when HF_SPACE_ID is set)
# =========================


# =========================
# COMMANDS
# =========================
@bot.message_handler(commands=["start"], func=is_allowed)
def start(m):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🧠 Квиз"),
        types.KeyboardButton("🗺️ Квест"),
        types.KeyboardButton("ℹ️ О боте"),
        types.KeyboardButton("🔄 Сброс"),
    )
    bot.send_message(
        m.chat.id,
        "👋 Привет! Я умею:\n"
        "• 🧠 *Квиз* — проверь свои знания\n"
        "• 🗺️ *Квест* — текстовое приключение\n"
        "• 💬 Просто напиши мне что-нибудь!\n\n"
        "Выбери действие или задай вопрос:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@bot.message_handler(commands=["about"], func=is_allowed)
def about_cmd(m):
    cmd_about(m)


@bot.message_handler(commands=["reset"], func=is_allowed)
def reset(m):
    clear_history(m.from_user.id)
    bot.send_message(m.chat.id, "cleared")


@bot.message_handler(commands=["quiz"], func=is_allowed)
def quiz_cmd(m):
    show_topic_menu(bot, m.chat.id)


@bot.message_handler(commands=["quest"], func=is_allowed)
def quest_cmd(m):
    show_genre_menu(bot, m.chat.id)


# =========================
# KEYBOARD BUTTONS
# =========================
@bot.message_handler(
    content_types=["text"],
    func=lambda m: is_allowed(m) and m.text in ("🧠 Квиз",),
)
def quiz_button(m):
    show_topic_menu(bot, m.chat.id)


@bot.message_handler(
    content_types=["text"],
    func=lambda m: is_allowed(m) and m.text in ("🗺️ Квест",),
)
def quest_button(m):
    show_genre_menu(bot, m.chat.id)


@bot.message_handler(
    content_types=["text"],
    func=lambda m: is_allowed(m) and m.text in ("ℹ️ О боте",),
)
def about_button(m):
    cmd_about(m)


@bot.message_handler(
    content_types=["text"],
    func=lambda m: is_allowed(m) and m.text in ("🔄 Сброс",),
)
def reset_button(m):
    clear_history(m.from_user.id)
    bot.send_message(m.chat.id, "cleared")


# =========================
# MODEL REGISTRATION (CRITICAL FIX)
# =========================
# MUST be dynamic at runtime (tests change config)
def _register_model():
    if getattr(config, "HF_SPACE_ID", ""):
        def cmd_model(m):
            parts = m.text.split()

            if len(parts) == 1:
                current = get_provider()
                bot.send_message(
                    m.chat.id,
                    f"Current provider: {current}\nSwitch: /model main  or  /model hf"
                )
                return

            provider = parts[1].lower()

            if provider not in ("main", "hf"):
                bot.send_message(m.chat.id, "Invalid choice")
                return

            ok = set_provider(m.from_user.id, provider)

            if not ok:
                bot.send_message(m.chat.id, "Could not save provider")
                return

            if provider == "hf":
                bot.send_message(m.chat.id, "Provider changed to Armenian (hf)")
            else:
                bot.send_message(m.chat.id, "Provider changed to Main")

        # Expose as module attribute so tests can retrieve it via getattr
        import sys
        sys.modules[__name__].cmd_model = cmd_model  # noqa

        @bot.message_handler(commands=["model"], func=is_allowed)
        def model_cmd(m):
            cmd_model(m)

_register_model()


# =========================
# CHAT
# =========================
@bot.message_handler(content_types=["text"], func=is_allowed)
def chat(m):
    return handle_message(m)


# =========================
# QUIZ & QUEST
# =========================
register_quiz(bot, ask_ai)
register_quest(bot, ask_ai)
