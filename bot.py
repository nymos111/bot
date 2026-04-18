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
        await bot.send_message(session.chat_id, "❌ Мало игроков. Игра отменена.")
        sessions.pop(session.chat_id, None)
    else:
        await bot.send_message(session.chat_id, "⏰ Лобби закрыто. Пишите /go")

@dp.message(Command("join"), F.chat.type.in_({"group", "supergroup"}))
async def join_game(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.lobby_open:
        return await message.answer("Лобби закрыто.")
    if message.from_user.id in session.players:
        return await message.answer("Вы уже в игре.")
    session.players[message.from_user.id] = Player(message.from_user)
    await message.answer(f"✅ {message.from_user.first_name} присоединился.")

@dp.message(Command("go"), F.chat.type.in_({"group", "supergroup"}))
async def start_game(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or session.started:
        return
    if len(session.players) < 3:
        return await message.answer("Нужно минимум 3 игрока.")

    session.started = True
    session.paused = False
    assign_roles(session)

    # Отправка ролей в ЛС
    for p in session.players.values():
        role_msg = {"Предатель": "🔴 Ты — ПРЕДАТЕЛЬ", "Детектив": "🔍 Ты — ДЕТЕКТИВ", "Врач": "🩹 Ты — ВРАЧ", "Шпион": "👁️ Ты — ШПИОН"}.get(p.role, "🟢 Обычный игрок")
        try:
            await bot.send_message(p.id, role_msg)
        except: pass

    await message.answer("🎮 Игра началась! Первая ситуация уже в чате.")
    await send_new_situation(session)   # ← сразу первая ситуация

# ================= NEW SITUATION =================
async def send_new_situation(session: Session):
    if not session.started or session.paused:
        return

    data = safe_generate(f"Жанр: {session.genre}\nТекущий хаос: {sum(p.chaos for p in session.players.values() if not p.dead)}")
    session.current_situation = data["situation"]

    await bot.send_message(session.chat_id, f"📍 **Ситуация:**\n{data['situation']}")

    # Отправляем варианты каждому игроку в ЛС
    session.player_choices.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"choice_{i}")]
        for i, opt in enumerate(data["options"])
    ])

    for p in session.players.values():
        if not p.dead:
            try:
                await bot.send_message(p.id, "Выберите действие:", reply_markup=kb)
            except: pass

    # Ждём 50 секунд на выбор
    await asyncio.sleep(50)
    await process_choices(session, data["options"])

# ================= PROCESS CHOICES =================
async def process_choices(session: Session, options: list):
    if not session.player_choices:
        await bot.send_message(session.chat_id, "Никто не сделал выбор. Ситуация усложняется...")
    
    # Увеличиваем хаос предателю
    for pid, choice_idx in session.player_choices.items():
        player = session.players.get(pid)
        if player and player.id == session.traitor_id:
            player.chaos += 2

    await send_new_situation(session)   # следующая ситуация

# ================= CHOICE HANDLER =================
@dp.callback_query(lambda c: c.data.startswith("choice_"))
async def handle_choice(callback: CallbackQuery):
    session = next((s for s in sessions.values() if callback.from_user.id in s.players), None)
    if not session or not session.current_situation or session.paused:
        return await callback.answer("Игра неактивна")

    choice_idx = int(callback.data.split("_")[1])
    session.player_choices[callback.from_user.id] = choice_idx
    await callback.answer("✅ Выбор принят", show_alert=False)

# ================= STOP / RESUME =================
@dp.message(Command("stop"), F.chat.type.in_({"group", "supergroup"}))
async def stop_game(message: types.Message):
    session = sessions.get(message.chat.id)
    if not session or not session.started:
        return await message.answer("Игра не запущена.")
    session.paused = True
    await message.answe
