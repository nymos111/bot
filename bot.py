import asyncio
import logging
import os
import time
import random

import requests
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= INIT =================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= AI =================

def safe_generate(prompt: str) -> str:
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemma-4-31b-it:free",
                "messages": [
                    {
                        "role": "system",
                        "content": """Ты режиссёр истории.
Пиши 1-2 коротких атмосферных предложения.
Не объясняй. Не пиши длинно."""
                    },
                    {"role": "user", "content": prompt[:2000]},
                ],
                "temperature": 0.9,
                "max_tokens": 120,
            },
            timeout=10
        )

        data = response.json()
        text = data["choices"][0]["message"]["content"].strip()

        if not text or len(text) < 5:
            return "Тишина становится напряжённой."

        return text[:300]

    except Exception as e:
        logging.error(f"AI ERROR: {e}")
        return random.choice([
            "Напряжение растёт.",
            "Кто-то явно скрывает правду.",
            "Атмосфера становится тяжелее."
        ])

# ================= DATA =================

class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.trust = 0
        self.suspicion = 0
        self.chaos = 0

class Session:
    def __init__(self, genre):
        self.genre = genre
        self.players = {}
        self.messages = []
        self.last_bot_time = 0
        self.round_active = False
        self.choices = {}

sessions = {}

# ================= HELPERS =================

def analyze(player, text):
    t = text.lower()
    if "не верю" in t:
        player.suspicion += 1
    if "давай" in t:
        player.trust += 1
    if "убить" in t:
        player.chaos += 1

def should_trigger(session):
    return (
        len(session.messages) >= 5 and
        time.time() - session.last_bot_time > 60
    )

async def ensure_player(session, user):
    if user.id not in session.players:
        session.players[user.id] = Player(user)
        try:
            await bot.send_message(user.id, "Ты участвуешь в истории.")
        except:
            pass

# ================= COMMANDS =================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот работает. В группе напиши /story")

@dp.message(Command("story"))
async def start_story(message: types.Message):
    genre = message.text.replace("/story", "").strip() or "драма"
    sessions[message.chat.id] = Session(genre)
    await message.answer(f"История началась ({genre}).")

@dp.message(Command("endstory"))
async def end_story(message: types.Message):
    if message.chat.id in sessions:
        sessions.pop(message.chat.id)
        await message.answer("История завершена.")

# ================= ROUND =================

ACTIONS = ["Исследовать", "Довериться", "Скрыть", "Действовать одному"]

async def start_round(chat_id):
    session = sessions.get(chat_id)
    if not session or session.round_active:
        return

    session.round_active = True
    session.choices = {}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=a, callback_data=f"c:{a}")]
        for a in ACTIONS
    ])

    for p in session.players.values():
        try:
            await bot.send_message(p.id, "Выбери действие:", reply_markup=kb)
        except:
            pass

    await asyncio.sleep(25)
    await resolve_round(chat_id)

async def resolve_round(chat_id):
    session = sessions.get(chat_id)
    if not session:
        return

    session.round_active = False

    text = "\n".join(
        f"{session.players[uid].name}: {c}"
        for uid, c in session.choices.items()
    )

    prompt = f"Жанр: {session.genre}\n{text}\nСобытие:"
    result = safe_generate(prompt)

    await bot.send_message(chat_id, result)
    session.last_bot_time = time.time()

@dp.callback_query(F.data.startswith("c:"))
async def choice(callback: types.CallbackQuery):
    uid = callback.from_user.id

    for s in sessions.values():
        if uid in s.players:
            s.choices[uid] = callback.data[2:]

    await callback.answer("Принято")

# ================= GROUP =================

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not message.text:
        return

    print("MSG:", message.text)

    await ensure_player(session, message.from_user)

    player = session.players[message.from_user.id]
    text = message.text[:300]

    session.messages.append(text)
    analyze(player, text)

    session.messages = session.messages[-20:]

    if not should_trigger(session):
        return

    context = "\n".join(session.messages[-10:])
    prompt = f"Жанр: {session.genre}\nЧат:\n{context}\nСобытие:"

    result = safe_generate(prompt)

    await message.answer(result)
    session.last_bot_time = time.time()

    if random.random() < 0.4:
        asyncio.create_task(start_round(message.chat.id))

# ================= RUN =================

async def main():
    logging.basicConfig(level=logging.INFO)
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
