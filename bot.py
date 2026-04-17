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
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemma-4-31b-it:free",
                "messages": [
                    {"role": "system", "content":
                     "Ты режиссёр истории. Пиши 1-2 коротких атмосферных предложения."},
                    {"role": "user", "content": prompt[:2000]}
                ],
                "temperature": 0.9,
                "max_tokens": 120
            },
            timeout=10
        )
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        return text[:300] if text else "История начинается..."
    except:
        return "Тишина сгущается..."

# ================= DATA =================

class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.role = None

class Session:
    def __init__(self, genre):
        self.genre = genre
        self.players = {}
        self.started = False

sessions = {}

ROLES = ["Лидер", "Предатель", "Наблюдатель"]

# ================= COMMANDS =================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Ты зарегистрирован. Вернись в чат.")

@dp.message(Command("story"))
async def start_story(message: types.Message):
    genre = message.text.replace("/story", "").strip() or "драма"

    session = Session(genre)
    sessions[message.chat.id] = session

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Начать игру", url=f"https://t.me/{(await bot.get_me()).username}")]
    ])

    await message.answer(
        f"Игра создаётся ({genre})\n"
        "Нажмите кнопку и напишите боту /start",
        reply_markup=kb
    )

@dp.message(Command("go"))
async def force_start(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return

    if len(session.players) == 0:
        await message.answer("Нет игроков.")
        return

    session.started = True

    # раздача ролей
    for p in session.players.values():
        p.role = random.choice(ROLES)
        try:
            await bot.send_message(p.id, f"Твоя роль: {p.role}")
        except:
            pass

    # старт сюжета
    intro = safe_generate(f"Жанр: {session.genre}\nНачни историю:")
    await message.answer(intro)

# ================= REGISTRATION =================

@dp.message(F.chat.type == "private")
async def private_handler(message: types.Message):
    user = message.from_user

    for chat_id, session in sessions.items():
        if not session.started:
            session.players[user.id] = Player(user)
            await message.answer("Ты добавлен в игру.")
            return

    await message.answer("Нет активной игры.")

# ================= GROUP STORY =================

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_handler(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.started:
        return

    if random.random() < 0.2:
        text = message.text or ""
        prompt = f"Жанр: {session.genre}\nСообщение: {text}\nСобытие:"
        result = safe_generate(prompt)
        await message.answer(result)

# ================= RUN =================

async def main():
    logging.basicConfig(level=logging.INFO)
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
