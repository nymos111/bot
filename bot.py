import asyncio
import logging
import os
import time
import random
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BotCommand, ChatPermissions

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
        self.dead = False

class Session:
    def __init__(self, chat_id, genre):
        self.chat_id = chat_id
        self.genre = genre
        self.players = {}
        self.started = False
        self.lobby_open = True
        self.traitor_id = None
        self.votes = {}
        self.start_time = time.time()

sessions = {}

# ================= COMMANDS =================
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="story", description="Создать игру"),
        BotCommand(command="join", description="Войти"),
        BotCommand(command="go", description="Начать"),
        BotCommand(command="vote", description="Голосование"),
        BotCommand(command="kick", description="Исключить"),
    ])

# ================= ROLE =================
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

# ================= STORY =================
@dp.message(Command("story"), F.chat.type.in_({"group", "supergroup"}))
async def story(message: types.Message):
    genre = message.text.replace("/story", "").strip() or "детектив"

    session = Session(message.chat.id, genre)
    sessions[message.chat.id] = session

    await message.answer("🎮 Лобби открыто (60 сек). Напишите /join")

    asyncio.create_task(lobby_timer(session))


async def lobby_timer(session):
    await asyncio.sleep(60)

    if session.started:
        return

    session.lobby_open = False

    if len(session.players) < 3:
        await bot.send_message(session.chat_id, "Недостаточно игроков. Игра отменена.")
        sessions.pop(session.chat_id, None)
    else:
        await bot.send_message(session.chat_id, "Лобби закрыто. Запускайте /go")

# ================= JOIN =================
@dp.message(Command("join"), F.chat.type.in_({"group", "supergroup"}))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session or not session.lobby_open:
        return await message.answer("Лобби закрыто.")

    if message.from_user.id in session.players:
        return await message.answer("Ты уже в игре.")

    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(f"{message.from_user.first_name} вошёл в игру.")

# ================= START =================
@dp.message(Command("go"), F.chat.type.in_({"group", "supergroup"}))
async def go(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session or session.started:
        return

    if len(session.players) < 3:
        return await message.answer("Нужно минимум 3 игрока.")

    session.started = True
    session.lobby_open = False

    assign_roles(session)

    for p in session.players.values():
        try:
            await bot.send_message(p.id, f"Твоя роль: {p.role}")
        except:
            pass

    intro = safe_generate(f"{session.genre} начало истории")
    await message.answer(f"Игра началась\n{intro}")

    asyncio.create_task(game_loop(session))

# ================= VOTE =================
@dp.message(Command("vote"), F.chat.type.in_({"group", "supergroup"}))
async def vote(message: types.Message):
    s = sessions.get(message.chat.id)
    if not s or not s.started:
        return

    s.votes = {}
    await message.answer("Голосование началось. /vote @user")

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
    player = s.players[kicked]

    player.dead = True

    # мут
    try:
        await bot.restrict_chat_member(
            s.chat_id,
            kicked,
            ChatPermissions(can_send_messages=False)
        )
    except:
        pass

    if kicked == s.traitor_id:
        await message.answer("Предатель найден. Победа игроков")
        s.started = False
        return

    await message.answer(f"{player.name} исключён и замолкает...")

# ================= GAME LOOP =================
async def game_loop(session):
    for _ in range(8):
        await asyncio.sleep(20)

        if not session.started:
            return

        chaos = sum(p.chaos for p in session.players.values() if not p.dead)
        trust = sum(p.trust for p in session.players.values() if not p.dead)

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

# ================= MUTE DEAD =================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def mute_dead(message: types.Message):
    s = sessions.get(message.chat.id)
    if not s or not s.started:
        return

    p = s.players.get(message.from_user.id)
    if p and p.dead:
        try:
            await message.delete()
        except:
            pass

# ================= RUN =================
async def main():
    await set_commands()
    logging.basicConfig(level=logging.INFO)
    print("BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
