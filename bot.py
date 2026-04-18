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
async def safe_generate(prompt: str) -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "google/gemma-4-31b-it:free",
                    "messages": [
                        {"role": "system", "content": """Ты — Game Master.
Возвращай строго JSON:
{
 "situation": "описание",
 "options": ["1","2","3","4"]
}"""},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 400
                },
                timeout=15
            ) as r:
                data = await r.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
    except:
        return {
            "situation": "Вы в опасной ситуации. Нужно действовать.",
            "options": ["Осмотреться", "Спрятаться", "Идти вперед", "Ждать"]
        }

# ================= DATA =================
class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.role = "Игрок"
        self.dead = False
        self.vote = None
        self.action_used = False

class Session:
    def __init__(self, chat_id, genre):
        self.chat_id = chat_id
        self.genre = genre
        self.players = {}
        self.started = False
        self.paused = False
        self.lobby_open = True
        self.traitor_id = None
        self.creator_id = None
        self.choices = {}
        self.votes = {}
        self.round = 0

sessions = {}

# ================= ROLES =================
def assign_roles(session):
    ids = list(session.players.keys())
    random.shuffle(ids)

    session.traitor_id = ids[0]
    session.players[ids[0]].role = "Предатель"

    if len(ids) >= 4:
        session.players[ids[1]].role = "Детектив"
    if len(ids) >= 5:
        session.players[ids[2]].role = "Врач"
    if len(ids) >= 6:
        session.players[ids[3]].role = "Шпион"

# ================= UTILS =================
def alive_players(session):
    return [p for p in session.players.values() if not p.dead]

def check_win(session):
    alive = alive_players(session)
    traitor_alive = any(p.id == session.traitor_id and not p.dead for p in alive)

    if not traitor_alive:
        return "Игроки победили"
    if len(alive) <= 2:
        return "Предатель победил"
    return None

# ================= COMMANDS =================
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="story", description="Создать игру"),
        BotCommand(command="join", description="Войти"),
        BotCommand(command="go", description="Старт"),
    ])

# ================= GAME =================
async def game_loop(session):
    while session.started and not session.paused:
        session.round += 1

        # ---- СИТУАЦИЯ ----
        data = await safe_generate(f"Жанр: {session.genre}, раунд {session.round}")
        await bot.send_message(
            session.chat_id,
            f"📍 <b>Раунд {session.round}</b>\n{data['situation']}",
            parse_mode="HTML"
        )

        # ---- ВЫБОРЫ ----
        session.choices.clear()

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=opt, callback_data=f"choice_{i}")]
            for i, opt in enumerate(data["options"])
        ])

        for p in alive_players(session):
            try:
                await bot.send_message(p.id, "Выберите действие:", reply_markup=kb)
            except:
                pass

        # ожидание
        for _ in range(40):
            if len(session.choices) >= len(alive_players(session)):
                break
            await asyncio.sleep(1)

        await bot.send_message(session.chat_id, "💬 Обсуждение (20 сек)")
        await asyncio.sleep(20)

        # ---- ГОЛОСОВАНИЕ ----
        session.votes.clear()

        alive = alive_players(session)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=p.name, callback_data=f"vote_{p.id}")]
            for p in alive
        ])

        for p in alive:
            try:
                await bot.send_message(p.id, "Голосуй:", reply_markup=kb)
            except:
                pass

        for _ in range(30):
            if len(session.votes) >= len(alive):
                break
            await asyncio.sleep(1)

        # подсчёт голосов
        vote_count = {}
        for v in session.votes.values():
            vote_count[v] = vote_count.get(v, 0) + 1

        result_text = "📊 Голосование:\n"
        for pid, count in vote_count.items():
            name = session.players[pid].name
            result_text += f"{name}: {count}\n"

        if vote_count:
            killed_id = max(vote_count, key=vote_count.get)
            session.players[killed_id].dead = True
            result_text += f"\n☠️ Убит: {session.players[killed_id].name}"

        await bot.send_message(session.chat_id, result_text)

        # ---- НОЧЬ ----
        await process_night(session)

        # ---- ПРОВЕРКА ПОБЕДЫ ----
        win = check_win(session)
        if win:
            await bot.send_message(session.chat_id, f"🏁 {win}")
            session.started = False
            break

# ================= NIGHT =================
async def process_night(session):
    target = None
    heal = None

    for p in alive_players(session):
        if p.role == "Предатель":
            target = random.choice(alive_players(session)).id
        if p.role == "Врач":
            heal = random.choice(alive_players(session)).id

    if target and target != heal:
        session.players[target].dead = True
        await bot.send_message(session.chat_id, f"🌙 Ночью убит {session.players[target].name}")
    else:
        await bot.send_message(session.chat_id, "🌙 Никто не погиб")

# ================= HANDLERS =================
@dp.message(Command("story"), F.chat.type.in_({"group", "supergroup"}))
async def story(message: types.Message):
    session = Session(message.chat.id, "ужасы")
    session.creator_id = message.from_user.id
    sessions[message.chat.id] = session

    await message.answer("Игра создана. /join (60 сек)")
    asyncio.create_task(lobby_timer(session))

async def lobby_timer(session):
    await asyncio.sleep(60)
    session.lobby_open = False

@dp.message(Command("join"))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.lobby_open:
        return

    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(f"{message.from_user.first_name} вошёл")

@dp.message(Command("go"))
async def go(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session:
        return

    session.started = True
    assign_roles(session)

    for p in session.players.values():
        try:
            await bot.send_message(p.id, f"Твоя роль: {p.role}")
        except:
            pass

    asyncio.create_task(game_loop(session))

@dp.callback_query(lambda c: c.data.startswith("choice_"))
async def choice(callback: CallbackQuery):
    session = next((s for s in sessions.values() if callback.from_user.id in s.players), None)
    if not session:
        return

    if callback.from
