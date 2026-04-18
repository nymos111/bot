import asyncio
import logging
import os
import random
import requests
import json
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
def safe_generate(prompt: str) -> dict:
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "google/gemma-4-31b-it:free",
                "messages": [
                    {"role": "system", "content": """Ты — Game Master. 
                    Всегда возвращай строго JSON:
                    {
                      "situation": "короткое атмосферное описание текущей ситуации",
                      "options": ["Вариант действия 1", "Вариант действия 2", "Вариант действия 3", "Вариант действия 4"]
                    }"""},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 400,
                "temperature": 0.7
            },
            timeout=15
        )
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except:
        # Нейтральный fallback без "тишины"
        return {
            "situation": "Вы находитесь в неизвестном месте. Что будете делать дальше?",
            "options": ["Осмотреть окружение", "Поговорить с остальными", "Попытаться найти выход", "Подождать развития событий"]
        }

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
        self.used_ability = False

class Session:
    def __init__(self, chat_id, genre):
        self.chat_id = chat_id
        self.genre = genre
        self.players: dict[int, Player] = {}
        self.started = False
        self.paused = False
        self.lobby_open = True
        self.traitor_id = None
        self.creator_id = None
        self.current_situation = None
        self.player_choices = {}   # player_id → выбранный индекс

sessions: dict[int, Session] = {}

# ================= COMMANDS =================
async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="story", description="Создать игру"),
        BotCommand(command="join", description="Присоединиться"),
        BotCommand(command="go", description="Начать игру"),
        BotCommand(command="stop", description="Прервать игру"),
        BotCommand(command="resume", description="Продолжить игру"),
    ])

def assign_roles(session):
    ids = list(session.players.keys())
    random.shuffle(ids)
    session.traitor_id = ids[0]
    session.players[ids[0]].role = "Предатель"
    if len(ids) >= 4: session.players[ids[1]].role = "Детектив"
    if len(ids) >= 5: session.players[ids[2]].role = "Врач"
    if len(ids) >= 6: session.players[ids[3]].role = "Шпион"

# ================= GAME START =================
@dp.message(Command("story"), F.chat.type.in_({"group", "supergroup"}))
async def create_story(message: types.Message):
    genre = message.text.replace("/story", "").strip() or "запертом доме"
    session = Session(message.chat.id, genre)
    session.creator_id = message.from_user.id
    sessions[message.chat.id] = session
    await message.answer("🎮 Игра создана!\nЛобби открыто 60 секунд.\nУчастники: пишите /join")
    asyncio.create_task(lobby_timer(session))

async def lobby_timer(session):
    await asyncio.sleep(60)
    if session.started: return
    session.lobby_open = False
    if len(session.players) < 3:
        await bot.
