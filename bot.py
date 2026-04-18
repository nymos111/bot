import asyncio
import logging
import os
import random
import json
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================= AI =================
async def safe_generate(prompt):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "google/gemma-4-31b-it:free",
                    "messages": [
                        {"role": "system", "content": "Верни JSON с situation и options (4 варианта)"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7
                },
                timeout=15
            ) as r:
                data = await r.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
    except:
        return {
            "situation": "Вы в опасной ситуации.",
            "options": ["Осмотреться", "Спрятаться", "Идти", "Ждать"]
        }

# ================= DATA =================
class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.role = "Игрок"
        self.dead = False

class Session:
    def __init__(self, chat_id, genre):
        self.chat_id = chat_id
        self.genre = genre
        self.players = {}
        self.started = False
        self.lobby_open = True
        self.traitor_id = None
        self.choices = {}
        self.votes = {}
        self.round = 0

sessions = {}

# ================= ROLES =================
def assign_roles(session):
    ids = list(session.players.keys())
    random.shuffle(ids)

    if not ids:
        return

    session.traitor_id = ids[0]
    session.players[ids[0]].role = "Предатель"

# ================= UTILS =================
def alive_players(session):
    return [p for p in session.players.values() if not p.dead]

def check_win(session):
    alive = alive_players(session)

    traitor_alive = False
    for p in alive:
        if p.id == session.traitor_id:
            traitor_alive = True

    if not traitor_alive:
        return "Игроки победили"

    if len(alive) <= 2:
        return "Предатель победил"

    return None

# ================= GAME LOOP =================
async def game_loop(session):
    while session.started:
        session.round += 1

        data = await safe_generate("Жанр: " + session.genre)

        await bot.send_message(
            session.chat_id,
            "Раунд " + str(session.round) + "\n" + data["situation"]
        )

        session.choices = {}

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=opt, callback_data="choice_" + str(i))]
            for i, opt in enumerate(data["options"])
        ])

        for p in alive_players(session):
            try:
                await bot.send_message(p.id, "Выбери:", reply_markup=kb)
            except:
                pass

        # ожидание выбора
        for _ in range(30):
            if len(session.choices) >= len(alive_players(session)):
                break
            await asyncio.sleep(1)

        await bot.send_message(session.chat_id, "Обсуждение 15 сек")
        await asyncio.sleep(15)

        # голосование
        session.votes = {}

        alive = alive_players(session)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=p.name, callback_data="vote_" + str(p.id))]
            for p in alive:
                try:
                await bot.send_message(p.id, "Голосуй:", reply_markup=kb)
            except:
                pass

        for _ in range(20):
            if len(session.votes) >= len(alive):
                break
            await asyncio.sleep(1)

        # подсчёт голосов
        vote_count = {}

        for v in session.votes.values():
            vote_count[v] = vote_count.get(v, 0) + 1

        text = "Голосование:\n"

        for pid, count in vote_count.items():
            text += session.players[pid].name + ": " + str(count) + "\n"

        if vote_count:
            killed_id = max(vote_count, key=vote_count.get)
            session.players[killed_id].dead = True
            text += "Убит: " + session.players[killed_id].name

        await bot.send_message(session.chat_id, text)

        # ночь
        await process_night(session)

        win = check_win(session)
        if win:
            await bot.send_message(session.chat_id, win)
            session.started = False
            break

# ================= NIGHT =================
async def process_night(session):
    alive = alive_players(session)

    if not alive:
        return

    target = random.choice(alive).id

    if target != session.traitor_id:
        session.players[target].dead = True
        await bot.send_message(session.chat_id, "Ночью убит " + session.players[target].name)
    else:
        await bot.send_message(session.chat_id, "Никто не умер")

# ================= COMMANDS =================
@dp.message(Command("story"))
async def story(message: types.Message):
    session = Session(message.chat.id, "ужасы")
    sessions[message.chat.id] = session

    await message.answer("Создано. /join")

@dp.message(Command("join"))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return

    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(message.from_user.first_name + " вошёл")

@dp.message(Command("go"))
async def go(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return

    session.started = True
    assign_roles(session)

    for p in session.players.values():
        try:
            await bot.send_message(p.id, "Роль: " + p.role)
        except:
            pass

    asyncio.create_task(game_loop(session))

# ================= CALLBACKS =================
@dp.callback_query(lambda c: c.data.startswith("choice_"))
async def choice(callback: CallbackQuery):
    if not callback.from_user:
        return

    user_id = callback.from_user.id

    session = None
    for s in sessions.values():
        if user_id in s.players:
            session = s
            break

    if not session:
        return

    if user_id in session.choices:
        await callback.answer("Уже выбрал")
        return

    idx = int(callback.data.split("_")[1])
    session.choices[user_id] = idx

    await callback.answer("OK")

@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def vote(callback: CallbackQuery):
    if not callback.from_user:
        return

    user_id = callback.from_user.id

    session = None
    for s in sessions.values():
        if user_id in s.players:
            session = s
            break

    if not session:
        return

    if user_id in session.votes:
        await callback.answer("Уже голосовал")
        return

    target = int(callback.data.split("_")[1])
    session.votes[user_id] = target

    await callback.answer("Голос принят")

# ================= RUN =================
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

        for p in alive:
