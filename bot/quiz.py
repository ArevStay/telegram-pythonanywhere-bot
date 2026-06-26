"""
quiz.py - AI quiz module (template)

Integrate with your telebot project.
Replace generate_quiz() with your ask_ai JSON generation if desired.
"""
import json
from telebot import types

QUIZ_STATE = {}

def generate_quiz(ask_ai, user_id, topic):
    prompt=f"""Create a JSON quiz about: {topic}
Return ONLY JSON:
{{"title":"...","questions":[{{"question":"...","options":["","","",""],"correct":0,"explanation":"..."}}]}}"""
    txt=ask_ai(user_id,prompt)
    return json.loads(txt)

def start_quiz(bot, ask_ai, message, topic):
    quiz=generate_quiz(ask_ai,message.from_user.id,topic)
    QUIZ_STATE[message.chat.id]={"quiz":quiz,"i":0,"score":0}
    send_next(bot,message.chat.id)

def send_next(bot, chat_id):
    st=QUIZ_STATE[chat_id]
    if st["i"]>=len(st["quiz"]["questions"]):
        bot.send_message(chat_id,f'🏁 Finished! Score: {st["score"]}/{len(st["quiz"]["questions"])}')
        del QUIZ_STATE[chat_id]
        return
    q=st["quiz"]["questions"][st["i"]]
    bot.send_poll(chat_id,q["question"],q["options"],type="quiz",
                  correct_option_id=q["correct"],
                  explanation=q.get("explanation",""),
                  is_anonymous=False)

def register(bot, ask_ai):
    @bot.message_handler(commands=["quiz"])
    def quiz_cmd(message):
        parts=message.text.split(maxsplit=1)
        if len(parts)<2:
            bot.reply_to(message,"Usage: /quiz <topic>")
            return
        start_quiz(bot,ask_ai,message,parts[1])

    @bot.poll_answer_handler()
    def poll_answer(ans):
        # telebot does not directly map poll->chat; extend as needed.
        pass
