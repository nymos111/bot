import asyncio
import logging
import os
import random
import time
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

BOT_USERNAME = None

# ================= AI =================
async def safe_generate(prompt: str) -> str:
    def blocking():
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "google/gemma-4-31b-it:free",
                    "messages": [
                        {"role": "system", "content": "Ты ведущий социальной игры с предателем. Коротко, атмосферно, с интригой."},
                        {"role": "user", "content": prompt[:2000]}
                    ],
                    "max_tokens": 120,
                    "temperature": 0.8
                },
                timeout=10
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logging.warning(f"AI error: {e}")
            return None

    result = await asyncio.to_thread(blocking)
    if not result:
        return random.choice([
            "Все переглянулись. Что-то явно не так.",
            "Тишина стала подозрительной.",
            "Кто-то врёт. Вопрос — кто.",
        ])
    return result[:350]


# ================= DATA =================
class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.username = (user.username or user.first_name).lower()
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
        self.history = []
        self.votes = {}
        self.last_ai_time = 0


sessions = {}

# ================= COMMANDS =================
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="story", description="Создать игру"),
        BotCommand(command="join", description="Войти"),
        BotCommand(command="go", description="Начать"),
        BotCommand(command="vote", description="Голосование"),
        BotCommand(command="kick", description="Кик"),
    ])


# ================= ROLES =================
def assign_roles(session: Session):
    ids = list(session.players.keys())
    random.shuffle(ids)

    session.traitor_id = ids[0]
    session.players[ids[0]].role = "Предатель"

    if len(ids) >= 4:
        session.players[ids[1]].role = "Детектив"
    if len(ids) >= 5:
        session.players[ids[2]].role = "Врач"


# ================= LOBBY =================
@dp.message(Command("story"), F.chat.type.in_({"group", "supergroup"}))
async def story(message: types.Message):
    if message.chat.id in sessions:
        return await message.answer("❌ Игра уже есть.")

    genre = message.text.replace("/story", "").strip() or "детектив"
    session = Session(message.chat.id, genre)
    sessions[message.chat.id] = session

    await message.answer(f"🎮 Игра «{genre}» создана!\n/join (60 сек)")
    asyncio.create_task(lobby_timer(session))


async def lobby_timer(session: Session):
    await asyncio.sleep(60)

    if session.started or not session.lobby_open:
        return

    session.lobby_open = False

    if len(session.players) < 3:
        await bot.send_message(session.chat_id, "❌ Недостаточно игроков.")
        sessions.pop(session.chat_id, None)
    else:
        await bot.send_message(session.chat_id, "⏰ Лобби закрыто. /go")


@dp.message(Command("join"), F.chat.type.in_({"group", "supergroup"}))
async def join(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.lobby_open:
        return await message.answer("Лобби закрыто.")

    if message.from_user.id in session.players:
        return await message.answer("Ты уже в игре.")

    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(f"✅ {message.from_user.first_name} в игре.")


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

    # роли в ЛС
    for p in session.players.values():
        try:
            await bot.send_message(p.id, f"🎭 Твоя роль: {p.role}")
        except:
            pass

    intro = await safe_generate(f"Начало истории: {session.genre}")
    await message.answer(f"🔥 Игра началась!\n{intro}")

    asyncio.create_task(auto_end(session))


# ================= CHAT =================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def chat_handler(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.started or not message.text:
        return

    player = session.players.get(message.from_user.id)

    # не игрок
    if not player:
        return

    # мёртвый
    if player.dead:
        try:
            await message.delete()
        except:
            pass
        return

    text = message.text.lower()

    # проверка упоминания
    mentioned = BOT_USERNAME and f"@{BOT_USERNAME}" in text
    reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot.id

    if not (mentioned or reply_to_bot):
        return

    # кулдаун
    if time.time() - session.last_ai_time < 2:
        return
    session.last_ai_time = time.time()

    clean = message.text[:180].replace("\n", " ")

    session.history.append(f"{player.name}: {clean}")
    session.history = session.history[-10:]

    prompt = f"{session.genre}. События: {' | '.join(session.history)}"
    reply = await safe_generate(prompt)

    await message.answer(reply)
    session.history.append(f"Бот: {reply}")


# ================= VOTE =================
@dp.message(F.text.startswith("/vote @"))
async def vote_process(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.started:
        return

    voter = session.players.get(message.from_user.id)

    if not voter or voter.dead:
        return await message.answer("Ты не можешь голосовать.")

    if message.from_user.id in session.votes:
        return await message.answer("Ты уже голосовал.")

    target_name = message.text.split("@")[1].strip().lower()

    for p in session.players.values():
        if p.username == target_name and not p.dead:
            session.votes[message.from_user.id] = p.id
            return await message.answer("Голос принят.")

    await message.answer("Игрок не найден.")


@dp.message(Command("vote"))
async def vote(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.started:
        return
    session.votes = {}
    await message.answer("🗳 Голосование началось.")


# ================= KICK =================
@dp.message(Command("kick"))
async def kick(message: types.Message):
    session = sessions.get(message.chat.id)

    if not session or not session.started or not session.votes:
        return await message.answer("Нет голосования.")

    counts = {}
    for t in session.votes.values():
        counts[t] = counts.get(t, 0) + 1

    target = max(counts, key=counts.get)
    player = session.players[target]

    player.dead = True

    try:
        await bot.restrict_chat_member(
            session.chat_id,
            target,
            ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        logging.warning(f"mute error: {e}")

    if target == session.traitor_id:
        await message.answer("🎉 Предатель найден!")
        await cleanup(session)
    else:
        await message.answer(f"🚫 {player.name} выбыл.")


# ================= CLEANUP =================
async def cleanup(session: Session):
    for p in session.players.values():
        try:
            await bot.restrict_chat_member(
                session.chat_id,
                p.id,
                ChatPermissions(can_send_messages=True)
            )
        except:
            pass

    sessions.pop(session.chat_id, None)


# ================= AUTO END =================
async def auto_end(session: Session):
    await asyncio.sleep(600)

    if not session.started:
        return

    await bot.send_message(session.chat_id, "⏰ Время вышло.")
    await cleanup(session)


# ================= RUN =================
async def main():
    global BOT_USERNAME

    me = await bot.get_me()
    BOT_USERNAME = (me.username or "").lower()

    await set_commands()

    logging.basicConfig(level=logging.INFO)

    print(f"Бот запущен: @{BOT_USERNAME}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
