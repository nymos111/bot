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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= AI =================

def safe_generate(prompt):
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "google/gemma-4-31b-it:free",
                "messages": [
                    {"role": "system", "content": "Коротко продолжи сюжет."},
                    {"role": "user", "content": prompt[:2000]}
                ],
                "max_tokens": 100
            },
            timeout=10
        )
        return r.json()["choices"][0]["message"]["content"][:300]
    except:
        return "Что-то меняется в воздухе..."

# ================= DATA =================

class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.role = "Игрок"
        self.chaos = 0
        self.trust = 0

class Session:
    def __init__(self, chat_id, genre):
        self.chat_id = chat_id
        self.genre = genre
        self.players = {}
        self.started = False
        self.traitor_id = None
        self.messages = []
        self.start_time = time.time()

sessions = {}
user_to_session = {}  # FIX: привязка игрока к игре

# ================= COMMANDS =================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Ты готов к игре. Вернись в чат.")

@dp.message(Command("story"))
async def story(message: types.Message):
    genre = message.text.replace("/story", "").strip() or "драма"

    session = Session(message.chat.id, genre)
    sessions[message.chat.id] = session

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Войти в игру", url=f"https://t.me/{(await bot.get_me()).username}")]
    ])

    await message.answer(
        "Игра создана. Нажми кнопку и напиши /start боту.",
        reply_markup=kb
    )

@dp.message(Command("go"))
async def go(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session:
        return

    if len(session.players) < 2:
        await message.answer("Нужно минимум 2 игрока.")
        return

    session.started = True

    # выбираем предателя
    session.traitor_id = random.choice(list(session.players.keys()))

    for p in session.players.values():
        if p.id == session.traitor_id:
            p.role = "Предатель"
            text = "Ты предатель. Твоя цель — разрушить доверие."
        else:
            text = "Ты обычный игрок. Найди предателя."

        try:
            await bot.send_message(p.id, text)
        except:
            pass

    intro = safe_generate(f"Жанр: {session.genre}\nНачало истории:")
    await message.answer(intro)

    asyncio.create_task(game_loop(session))

# ================= REGISTRATION =================

@dp.message(F.chat.type == "private")
async def register(message: types.Message):
    user = message.from_user

    # FIX: ищем активную игру
    for session in sessions.values():
        if not session.started:
            session.players[user.id] = Player(user)
            user_to_session[user.id] = session.chat_id
            await message.answer("Ты зарегистрирован.")
            return

    await message.answer("Нет активной игры.")

# ================= GAME =================

async def game_loop(session):
    for _ in range(10):  # 10 ходов
        await asyncio.sleep(20)

        if not session.started:
            return

        # анализ сообщений
        chaos = 0
        trust = 0

        for msg in session.messages[-20:]:
            msg = msg.lower()
            if "подозр" in msg:
                chaos += 1
            if "вместе" in msg:
                trust += 1

        prompt = f"{session.genre}\nхаос={chaos} доверие={trust}"
        event = safe_generate(prompt)

        await bot.send_message(session.chat_id, event)

    await end_game(session)

async def end_game(session):
    chaos = sum(p.chaos for p in session.players.values())
    trust = sum(p.trust for p in session.players.values())

    if chaos > trust:
        result = "Предатель победил."
    else:
        result = "Игроки победили."

    await bot.send_message(session.chat_id, result)

    session.started = False

# ================= GROUP =================

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session or not session.started:
        return

    text = message.text or ""
    session.messages.append(text)

    player = session.players.get(message.from_user.id)

    if player:
        if "подозр" in text:
            player.chaos += 1
        if "довер" in text:
            player.trust += 1

# ================= RUN =================

async def main():
    logging.basicConfig(level=logging.INFO)
    print("STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
