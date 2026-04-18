import asyncio
import logging
import os
import time
import random
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand

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
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "google/gemma-4-31b-it:free",
                "messages": [
                    {"role": "system", "content": "Коротко и атмосферно продолжи сюжет."},
                    {"role": "user", "content": prompt[:2000]}
                ],
                "max_tokens": 120
            },
            timeout=10
        )
        return r.json()["choices"][0]["message"]["content"][:350]
    except:
        return "Тишина становится напряжённой..."

# ================= DATA =================
class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.username = user.username
        self.role = "Игрок"
        self.chaos = 0
        self.trust = 0
        self.used_ability = False

class Session:
    def __init__(self, chat_id, genre):
        self.chat_id = chat_id
        self.genre = genre
        self.players = {}
        self.started = False
        self.traitor_id = None
        self.creator_id = None
        self.messages = []
        self.votes = {}

sessions = {}

# ================= BOT COMMANDS =================
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="story", description="Создать игру"),
        BotCommand(command="join", description="Войти в игру"),
        BotCommand(command="go", description="Начать"),
        BotCommand(command="vote", description="Голосование"),
        BotCommand(command="kick", description="Исключить игрока"),
    ])

# ================= ROLE ASSIGN =================
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

# ================= COMMANDS =================
@dp.message(Command("start"))
async def start(message: types.Message):
    if message.chat.type == "private":
        await message.answer("Готов. Вернись в чат и нажми /join")

@dp.message(Command("story"), F.chat.type.in_({"group", "supergroup"}))
async def story(message: types.Message):
    genre = message.text.replace("/story", "").strip() or "детектив"

    session = Session(message.chat.id, genre)
    session.creator_id = message.from_user.id
    sessions[message.chat.id] = session

    await message.answer("🎮 Игра создана! Напишите /join")

@dp.message(Command("join"), F.chat.type.in_({"group", "supergroup"}))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session or session.started:
        return await message.answer("Нет активной игры.")

    if message.from_user.id in session.players:
        return await message.answer("Ты уже в игре.")

    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(f"{message.from_user.first_name} в игре.")

@dp.message(Command("go"), F.chat.type.in_({"group", "supergroup"}))
async def go(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session or session.started:
        return

    if len(session.players) < 3:
        return await message.answer("Нужно минимум 3 игрока.")

    session.started = True
    assign_roles(session)

    for p in session.players.values():
        if p.role == "Предатель":
            text = "🔴 Ты предатель. /sabotage"
        elif p.role == "Детектив":
            text = "🔍 Ты детектив. /investigate @user"
        elif p.role == "Врач":
            text = "🩹 Ты врач. /heal"
        elif p.role == "Шпион":
            text = "👁 Ты шпион. /peek"
        else:
            text = "🟢 Ты игрок."

        try:
            await bot.send_message(p.id, text)
        except:
            pass

    intro = safe_generate(f"{session.genre} начало истории")
    await message.answer(f"Игра началась\n{intro}")

    asyncio.create_task(game_loop(session))

# ================= ABILITIES =================
@dp.message(Command("sabotage"), F.chat.type == "private")
async def sabotage(message: types.Message):
    for s in sessions.values():
        if s.started and message.from_user.id in s.players:
            p = s.players[message.from_user.id]
            if p.role != "Предатель":
                return await message.answer("Ты не предатель.")
            p.chaos += 3
            return await message.answer("Хаос увеличен.")

@dp.message(Command("investigate"), F.chat.type == "private")
async def investigate(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        return

    target = args[1].replace("@", "")

    for s in sessions.values():
        if s.started and message.from_user.id in s.players:
            for p in s.players.values():
                if p.username == target:
                    if p.role == "Предатель":
                        return await message.answer("🔴 Подозрительный")
                    else:
                        return await message.answer("🟢 Чист")

@dp.message(Command("heal"), F.chat.type == "private")
async def heal(message: types.Message):
    for s in sessions.values():
        if s.started and message.from_user.id in s.players:
            p = s.players[message.from_user.id]
            if p.role != "Врач":
                return
            p.trust += 2
            return await message.answer("Доверие увеличено.")

@dp.message(Command("peek"), F.chat.type == "private")
async def peek(message: types.Message):
    for s in sessions.values():
        if s.started and message.from_user.id in s.players:
            target = random.choice(list(s.players.values()))
            return await message.answer(f"{target.name} ведёт себя странно...")

# ================= VOTE =================
@dp.message(Command("vote"), F.chat.type.in_({"group", "supergroup"}))
async def vote(message: types.Message):
    s = sessions.get(message.chat.id)
    if not s or not s.started:
        return

    s.votes = {}
    await message.answer("Голосование началось. Пиши /vote @user")

@dp.message(F.text.startswith("/vote @"))
async def vote_process(message: types.Message):
    s = sessions.get(message.chat.id)
    if not s or not s.started:
        return

    target = message.text.split("@")[1]

    for p in s.players.values():
        if p.username == target:
            s.votes[message.from_user.id] = p.id
            await message.answer("Голос принят")

# ================= KICK =================
@dp.message(Command("kick"), F.chat.type.in_({"group", "supergroup"}))
async def kick(message: types.Message):
    s = sessions.get(message.chat.id)
    if not s or not s.started:
        return

    if not s.votes:
        return await message.answer("Нет голосов")

    counts = {}
    for v in s.votes.values():
        counts[v] = counts.get(v, 0) + 1

    kicked = max(counts, key=counts.get)

    if kicked == s.traitor_id:
        await message.answer("Предатель найден. Победа игроков")
        s.started = False
        return

    del s.players[kicked]
    await message.answer("Игрок исключён")

# ================= GAME LOOP =================
async def game_loop(session):
    for _ in range(8):
        await asyncio.sleep(20)

        if not session.started:
            return

        chaos = sum(p.chaos for p in session.players.values())
        trust = sum(p.trust for p in session.players.values())

        text = safe_generate(f"{session.genre} хаос={chaos} доверие={trust}")
        await bot.send_message(session.chat_id, text)

    await end_game(session)

async def end_game(session):
    chaos = sum(p.chaos for p in session.players.values())
    trust = sum(p.trust for p in session.players.values())

    if chaos > trust:
        await bot.send_message(session.chat_id, "Предатель победил")
    else:
        await bot.send_message(session.chat_id, "Игроки победили")

    session.started = False

# ================= RUN =================
async def main():
    await set_commands()
    logging.basicConfig(level=logging.INFO)
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
