import asyncio
import logging
import os
import random
import json
import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

sessions = {}

async def safe_generate(prompt):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://local.game",
                    "X-Title": "TwistRealm"
                },
                json={
                    "model": "google/gemma-4-31b-it:free",
                    "messages": [
                        {
                            "role": "system",
                            "content": """Ты ведущий игры. Отвечай строго JSON:
{
 "situation": "описание",
 "options": ["1","2","3","4"]
}"""
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.9
                }
            ) as r:
                data = await r.json()
                content = data["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                return json.loads(content[start:end])
    except:
        return {
            "situation": "Реальность искажается вокруг вас.",
            "options": ["Осмотреться", "Бежать", "Кричать", "Спрятаться"]
        }

class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.role = "Игрок"
        self.dead = False

class Session:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = {}
        self.started = False
        self.traitor_id = None
        self.history = []
        self.choices = {}
        self.votes = {}
        self.round = 0
        self.kill_target = None
        self.heal_target = None
        self.check_target = None

def alive(session):
    return [p for p in session.players.values() if not p.dead]

def assign_roles(session):
    ids = list(session.players.keys())
    random.shuffle(ids)
    if not ids:
        return
    session.traitor_id = ids[0]
    session.players[ids[0]].role = "Предатель"
    if len(ids) > 3:
        session.players[ids[1]].role = "Детектив"
    if len(ids) > 4:
        session.players[ids[2]].role = "Врач"

def win_check(session):
    alive_players = alive(session)
    traitor_alive = any(p.id == session.traitor_id and not p.dead for p in alive_players)
    if not traitor_alive:
        return "Игроки победили"
    if len(alive_players) <= 2:
        return "Предатель победил"
    return None

async def game_loop(session):
    while session.started:
        session.round += 1

        context = " ".join(session.history[-5:])
        data = await safe_generate(context)

        session.history.append(data["situation"])

        await bot.send_message(
            session.chat_id,
            f"Раунд {session.round}\n{data['situation']}"
        )

        session.choices = {}

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=o, callback_data=f"choice_{i}")]
            for i, o in enumerate(data["options"])
        ])

        for p in alive(session):
            try:
                await bot.send_message(p.id, "Действие:", reply_markup=kb)
            except:
                pass

        for _ in range(30):
            if len(session.choices) >= len(alive(session)):
                break
            await asyncio.sleep(1)

        await bot.send_message(session.chat_id, "Обсуждение 15 сек")
        await asyncio.sleep(15)

        session.votes = {}

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=p.name, callback_data=f"vote_{p.id}")]
            for p in alive(session)
        ])

        for p in alive(session):
            try:
                await bot.send_message(p.id, "Голосуй:", reply_markup=kb)
            except:
                pass

        for _ in range(20):
            if len(session.votes) >= len(alive(session)):
                break
            await asyncio.sleep(1)

        vote_count = {}
        for v in session.votes.values():
            vote_count[v] = vote_count.get(v, 0) + 1

        text = "Голосование:\n"
        for pid, count in vote_count.items():
            text += session.players[pid].name + ": " + str(count) + "\n"

        if vote_count:
            killed = max(vote_count, key=vote_count.get)
            session.players[killed].dead = True
            text += "Казнён: " + session.players[killed].name

        await bot.send_message(session.chat_id, text)

        session.kill_target = None
        session.heal_target = None
        session.check_target = None

        for p in alive(session):
            if p.role == "Предатель":
                targets = [pl for pl in alive(session) if pl.id != p.id]
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"kill_{t.id}")]
                    for t in targets
                ])
                try:
                    await bot.send_message(p.id, "Кого убить:", reply_markup=kb)
                except:
                    pass

            if p.role == "Врач":
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"heal_{t.id}")]
                    for t in alive(session)
                ])
                try:
                    await bot.send_message(p.id, "Кого лечить:", reply_markup=kb)
                except:
                    pass

            if p.role == "Детектив":
                targets = [pl for pl in alive(session) if pl.id != p.id]
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"check_{t.id}")]
                    for t in targets
                ])
                try:
                    await bot.send_message(p.id, "Кого проверить:", reply_markup=kb)
                except:
                    pass

        await asyncio.sleep(20)

        if session.check_target:
            role = session.players[session.check_target].role
            detective = next((p for p in session.players.values() if p.role == "Детектив"), None)
            if detective:
                try:
                    await bot.send_message(detective.id, f"Роль: {role}")
                except:
                    pass

        if session.kill_target and session.kill_target != session.heal_target:
            session.players[session.kill_target].dead = True
            await bot.send_message(session.chat_id, f"Ночью убит {session.players[session.kill_target].name}")
        else:
            await bot.send_message(session.chat_id, "Ночью никто не умер")

        win = win_check(session)
        if win:
            await bot.send_message(session.chat_id, win)
            session.started = False
            break

@dp.message(Command("story"))
async def story(message: types.Message):
    sessions[message.chat.id] = Session(message.chat.id)
    await message.answer("Игра создана /join")

@dp.message(Command("join"))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return
    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(message.from_user.first_name + " в игре")

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

@dp.callback_query()
async def callbacks(callback: CallbackQuery):
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

    data = callback.data

    if data.startswith("choice_"):
        if user_id in session.choices:
            return await callback.answer("Уже выбрал")
        session.choices[user_id] = int(data.split("_")[1])
        await callback.answer("OK")

    elif data.startswith("vote_"):
        if user_id in session.votes:
            return await callback.answer("Уже голосовал")
        session.votes[user_id] = int(data.split("_")[1])
        await callback.answer("Голос принят")

    elif data.startswith("kill_"):
        if user_id != session.traitor_id:
            return
        session.kill_target = int(data.split("_")[1])
        await callback.answer("Цель выбрана")

    elif data.startswith("heal_"):
        player = session.players.get(user_id)
        if not player or player.role != "Врач":
            return
        session.heal_target = int(data.split("_")[1])
        await callback.answer("Лечение выбрано")

    elif data.startswith("check_"):
        player = session.players.get(user_id)
        if not player or player.role != "Детектив":
            return
        session.check_target = int(data.split("_")[1])
        await callback.answer("Проверка выбрана")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
