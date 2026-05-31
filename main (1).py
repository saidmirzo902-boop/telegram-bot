import asyncio
import os
import time
import random
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from dotenv import load_dotenv
from openai import OpenAI
from gtts import gTTS
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction
from datetime import datetime, timedelta
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = OpenAI(api_key=OPENAI_API_KEY)

user_modes = {}

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS premium_users (
    user_id INTEGER PRIMARY KEY,
    expire_date TEXT
)
""")

conn.commit()

def is_premium(user_id):

    cursor.execute(
        """
        SELECT expire_date
        FROM premium_users
        WHERE user_id=?
        """,
        (user_id,)
    )

    result = cursor.fetchone()

    if not result:
        return False

    expire_date = datetime.strptime(
        result[0],
        "%Y-%m-%d"
    )

    return expire_date >= datetime.now()

ADMIN_ID = 6511055106

grammar_topics = [
    "Present Simple",
    "Present Continuous",
    "Present Perfect",
    "Past Simple",
    "Past Continuous",
    "Past Perfect",
    "Future Simple",
    "Conditionals",
    "Passive Voice",
    "Reported Speech",
    "Modal Verbs"
]

@dp.message(CommandStart())
async def start(message: Message):

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Vocabulary"), KeyboardButton(text="📝 Grammar")],
            [KeyboardButton(text="📖 Reading"), KeyboardButton(text="🎤 Speaking")],
            [KeyboardButton(text="🎯 IELTS"), KeyboardButton(text="🤖 AI Teacher")],
            [KeyboardButton(text="🎙 Voice Chat"), KeyboardButton(text="⭐ Premium")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Welcome to English Master Bot 🇬🇧",
        reply_markup=keyboard
    )

@dp.message(lambda message: message.voice)
async def voice_message(message: Message):

    if user_modes.get(message.from_user.id) != "voice":
        return

    try:
        await message.answer("🎤 Processing voice...")

        voice = message.voice

        file = await bot.get_file(voice.file_id)

        os.makedirs("voices", exist_ok=True)

        voice_path = f"voices/{message.from_user.id}.ogg"

        await bot.download_file(
            file.file_path,
            destination=voice_path
        )

        with open(voice_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

        user_text = transcript.text

        await message.answer(f"📝 You said:\n\n{user_text}")

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-nano",
            input=f"""
        
        You are an English speaking tutor.

        The user MUST speak only English.

        If the user's message is not English:

        Reply ONLY:

        ❌ Please speak English only.

        If the user's message is English:

        1. Reply naturally.
        2. Correct mistakes.
        3. Explain briefly.
        4. Ask one follow-up question.

        User:

        {user_text}
        """
        )
        
        reply_text = response.output_text

        tts = gTTS(
            text=reply_text,
            lang="en"
        )

        audio_path = f"voices/{message.from_user.id}_reply.mp3"
        
        start = time.time()

        tts.save(audio_path)

        print("TTS time:", time.time() - start)
        
        await message.answer(reply_text[:3000])

        voice_file = FSInputFile(audio_path)

        await bot.send_voice(
            chat_id=message.chat.id,           
            voice=voice_file
        )

    except Exception as e:
        print(e)
        await message.answer(f"Error: {e}")

@dp.callback_query()
async def premium_callback(callback):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Not allowed",
            show_alert=True
        )
        return

    if callback.data.startswith("approve_"):

        user_id = int(
            callback.data.split("_")[1]
        )

        expire_date = (
            datetime.now() + timedelta(days=30)
        ).strftime("%Y-%m-%d")

        cursor.execute(
            """
            INSERT OR REPLACE INTO premium_users
            (user_id, expire_date)
            VALUES (?, ?)
            """,
            (user_id, expire_date)
        )

        conn.commit()

        await bot.send_message(
            user_id,
            f"🎉 Premium activated!\n\nValid until: {expire_date}"
        )

        await callback.message.edit_caption(
            caption=
            callback.message.caption +
            "\n\n✅ APPROVED"
        )

        await callback.answer(
            "Premium activated."
        )

        return

    if callback.data.startswith("reject_"):

        user_id = int(
            callback.data.split("_")[1]
        )

        await bot.send_message(
            user_id,
            "❌ Your payment was rejected.\nPlease contact admin."
        )

        await callback.message.edit_caption(
            caption=
            callback.message.caption +
            "\n\n❌ REJECTED"
        )

        await callback.answer(
            "Request rejected."
        )

@dp.message(lambda message: message.photo)
async def payment_screenshot(message: Message):
    
    if user_modes.get(message.from_user.id) != "payment":
         return

    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Approve",
        callback_data=f"approve_{message.from_user.id}"
    )

    builder.button(
        text="❌ Reject",
        callback_data=f"reject_{message.from_user.id}"
    )

    builder.adjust(2)

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=
        f"💳 New Premium Request\n\n"
        f"User ID: {message.from_user.id}\n"
        f"Name: {message.from_user.full_name}",
        reply_markup=builder.as_markup()
    )
  
    await message.answer(
        "✅ Screenshot sent to admin.\nPlease wait for confirmation."
    )

    user_modes.pop(message.from_user.id, None)

@dp.message()
async def chat(message: Message):

    text = message.text

    if text.startswith("/addpremium"):

        if message.from_user.id != ADMIN_ID:
            return

        try:
            user_id = int(text.split()[1])

            cursor.execute(
                "INSERT OR IGNORE INTO premium_users VALUES (?)",
                (user_id,)
            )

            conn.commit()

            await message.answer(
                f"✅ Premium added:\n{user_id}"
            )

        except:
            await message.answer(
                "Usage:\n/addpremium USER_ID"
            )

        return
    
    if text.startswith("/removepremium"):

        if message.from_user.id != ADMIN_ID:
            return

        try:
            user_id = int(text.split()[1])

            cursor.execute(
                "DELETE FROM premium_users WHERE user_id=?",
                (user_id,)
            )

            conn.commit()

            await message.answer(
                f"❌ Premium removed:\n{user_id}"
            )

        except:
            await message.answer(
                "Usage:\n/removepremium USER_ID"
            )

        return

    if text == "/listpremium":

        if message.from_user.id != ADMIN_ID:
            return

        cursor.execute(
            "SELECT user_id FROM premium_users"
        )

        users = cursor.fetchall()

        if not users:
            await message.answer(
                "No premium users."
            )
            return

        result = "⭐ Premium Users:\n\n"

        for user in users:
            result += f"{user[0]}\n"

        await message.answer(result)

        return
    
    if text == "📤 Send Payment Screenshot":

        user_modes[message.from_user.id] = "payment"

        await message.answer(
            "📸 Please send your payment screenshot."
        )
      
        return

    if text == "🎙 Voice Chat":

        user_modes[message.from_user.id] = "voice"

        await message.answer(
            "🎤 Send me a voice message in English."
        )
        return

    if text == "🤖 AI Teacher":

        user_modes[message.from_user.id] = "teacher"

        await message.answer(
            "Hello! I am your English teacher 🇬🇧\n\nWrite anything in English."
        )
        return

    if text == "📚 Vocabulary":

        user_modes[message.from_user.id] = "vocabulary"

        await message.answer(
            "Send me any English word.\n\nExample:\nambitious"
        )
        return
     
    if text == "📝 Grammar":

        grammar_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                 [KeyboardButton(text="Present Simple")],
                 [KeyboardButton(text="Present Continuous")],
                 [KeyboardButton(text="Present Perfect")],
                 [KeyboardButton(text="Past Simple")],
                 [KeyboardButton(text="Past Continuous")],
                 [KeyboardButton(text="Past Perfect")],
                 [KeyboardButton(text="Future Simple")],
                 [KeyboardButton(text="Conditionals")],
                 [KeyboardButton(text="Passive Voice")],
                 [KeyboardButton(text="Reported Speech")],
                 [KeyboardButton(text="Modal Verbs")],
                 [KeyboardButton(text="Back")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            "Choose a grammar topic:",
            reply_markup=grammar_keyboard
        )

        return

    if text == "📖 Reading":

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-mini",
            input="""
Create a realistic IELTS Academic Reading test.

Requirements:
- 300-500 words
- Academic topic
- IELTS style
- Include title
- Include 5 multiple choice questions
- Include 5 True/False/Not Given questions
- Do NOT show answers immediately
"""
    )

        await message.answer(response.output_text[:4000])

        return
   
    if text == "🎤 Speaking":

        speaking_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="IELTS Speaking")],
                [KeyboardButton(text="CEFR Speaking")],
                [KeyboardButton(text="Back")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            "Choose Speaking type:",
            reply_markup=speaking_keyboard
        )

        return
        
    if text == "IELTS Speaking":

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-nano",
            input="""
    You are an IELTS examiner.

    Generate:

    - IELTS Speaking Part 1 (5 questions)
    - IELTS Speaking Part 2 (1 cue card)
    - IELTS Speaking Part 3 (5 questions)

    Do not provide answers.
    """
        )

        await message.answer(response.output_text[:4000])

        return   

    if text == "CEFR Speaking":

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-nano",
            input="""
    Create a CEFR Speaking practice test.

    Include:

    - B1 level speaking questions
    - B2 level speaking questions
    - C1 level speaking questions

    10 questions total.

    Do not provide answers.
    """
        )

        await message.answer(response.output_text[:4000])

        return

    if text == "🎯 IELTS":

        ielts_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="IELTS Speaking")],
                [KeyboardButton(text="IELTS Writing")],
                [KeyboardButton(text="IELTS Reading Test")],
                [KeyboardButton(text="Back")]
            ],
            resize_keyboard=True
        
        )


        await message.answer(
            "Choose IELTS section:",
             reply_markup=ielts_keyboard
        )

        return

    if text == "IELTS Writing":

        if not is_premium(message.from_user.id):
            await message.answer(
                "🔒 This feature is Premium."
            )
            return

        await message.answer(
            "IELTS Writing Task 2:\n\nSome people think online learning is better than traditional learning. Discuss both views and give your opinion."
        )

        return


    if text == "IELTS Reading Test":

       await message.answer(
           "Use 📖 Reading button for full IELTS Reading tests."
       )

       return


    if text == "Band Score Checker":

       await message.answer(
           "Send me your IELTS Speaking or Writing answer and I will estimate your band score."
       )

       return

    if text == "⭐ Premium":

         premium_keyboard = ReplyKeyboardMarkup(
             keyboard=[
                 [KeyboardButton(text="🚀 Premium Features")],
                 [KeyboardButton(text="💳 Buy Premium")],
                 [KeyboardButton(text="📤 Send Payment Screenshot")],
                 [KeyboardButton(text="⭐ Check Status")],
                 [KeyboardButton(text="📞 Contact Admin")],
                 [KeyboardButton(text="Back")]
             ],
             resize_keyboard=True
         )

         await message.answer(
             "⭐ Premium Menu",
             reply_markup=premium_keyboard
         )

         return
    
    if text == "🚀 Premium Features":

        if not is_premium(message.from_user.id):
            await message.answer(
                "🔒 Premium required."
            )
            return

        premium_features_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🏆 IELTS Band Score")],
                [KeyboardButton(text="🎤 IELTS Speaking Score")],
                [KeyboardButton(text="🤖 AI Conversation Partner")],
                [KeyboardButton(text="📚 My Vocabulary Book")],
                [KeyboardButton(text="🔊 Pronunciation Trainer")],
                [KeyboardButton(text="📊 CEFR Level Test")],
                [KeyboardButton(text="Back")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            "🚀 Premium Features",
            reply_markup=premium_features_keyboard
        )

        return

    if text == "⭐ Check Status":

        if is_premium(message.from_user.id):
            await message.answer(
                "✅ You have Premium access."
            )
        else:
            await message.answer(
                "❌ You do not have Premium."
            )

        return

    if text == "💳 Buy Premium":

        await message.answer(
            "⭐ PREMIUM MEMBERSHIP\n\n"

            "🔥 Premium Features:\n\n"

            "✅ IELTS Writing Band Score Checker\n"
            "✅ IELTS Speaking Band Score\n"
            "✅ AI Conversation Partner\n"
            "✅ Advanced Grammar Teacher\n"
            "✅ Personal Vocabulary Book\n"
            "✅ Daily Vocabulary Plan\n"
            "✅ Pronunciation Trainer\n"
            "✅ CEFR Level Test\n"
            "✅ Advanced Reading Tests\n"
            "✅ Priority Support\n\n"

            "💰 Price: 50 000 UZS / Month\n\n"

            "💳 Card Number:\n"
            "5614683512720285\n\n"

            "After payment:\n"
            "📤 Send Payment Screenshot"
        )

        return
    
    if text == "🏆 IELTS Band Score":

        if not is_premium(message.from_user.id):
            await message.answer(
                "🔒 Premium feature."
            )
            return

        user_modes[message.from_user.id] = "band_score"

        await message.answer(
            "Send your IELTS Writing Task 1 or Task 2 answer."
        )

        return

    if text == "📞 Contact Admin":

        await message.answer(
            "@Saohell"
        )

        return

    if text == "Back":

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📚 Vocabulary"), KeyboardButton(text="📝 Grammar")],
                [KeyboardButton(text="📖 Reading"), KeyboardButton(text="🎤 Speaking")],
                [KeyboardButton(text="🎯 IELTS"), KeyboardButton(text="🤖 AI Teacher")],
                [KeyboardButton(text="🎙 Voice Chat"), KeyboardButton(text="⭐ Premium")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            "Main Menu",
            reply_markup=keyboard
        )

        return

    if text in grammar_topics:

        await bot.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.TYPING
        )

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-nano",
            input=f"""
You are an English grammar teacher.

Teach this grammar topic:

{text}

Requirements:
- Simple explanation
- Uzbek explanation
- Russian explanation
- Formula
- 10 examples
- Common mistakes
- Mini exercise with answers
"""
    )

        await message.answer(response.output_text[:4000])

        return


    mode = user_modes.get(message.from_user.id)

    if mode == "vocabulary":

        await bot.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.TYPING
        )

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-nano",
            input=f"""
Explain this English word:

{text}

Give:

1. Meaning
2. Uzbek translation
3. Russian translation
4. 3 example sentences
5. IELTS level
"""
    )

        await message.answer(response.output_text)

        return
    
    if mode == "band_score":

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-mini",
            input=f"""

    You are an IELTS examiner.

    Evaluate this IELTS Writing answer.

    {text}

    Give:

    Overall Band Score
    Task Response
    Coherence and Cohesion
    Lexical Resource
    Grammar Range and Accuracy

    Show mistakes and improvements.
    """
        )

        await message.answer(
           response.output_text[:4000]
        )

        return
       
    if mode == "teacher":
 
        await bot.send_chat_action(
            chat_id=message.chat.id,
            action=ChatAction.TYPING
        )

        response = await asyncio.to_thread(
            client.responses.create,
            model="gpt-5-mini",
            input=f"""
You are an English teacher.

Student wrote:
{text}

Correct grammar mistakes.
Explain mistakes briefly.
Reply naturally.
Ask one follow-up question.
"""
    )

        await message.answer(response.output_text)

        return

async def main():
    print("Bot started...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())