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
                            "content": """Ты — ведущий напряжённой психологической игры уровня Among Us + Мафия.
Создавай опасные ситуации, усиливай паранойю, намекай на предателя, учитывай прошлые события.

Формат строго JSON:
{
 "situation": "опасная ситуация",
 "options": ["действие 1", "действие 2", "действие 3", "действие 4"]
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
    except Exception:
        return {
            "situation": "Реальность трещит. Кто-то среди вас ведёт двойную игру.",
            "options": ["Осмотреться", "Обвинить кого-то", "Спрятаться", "Бежать"]
        }

class Player:
    def __init__(self, user):
        self.id = user.id
        self.name = user.first_name
        self.role = "Игрок"
        self.dead = False
        self.suspicion = 0

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
        self.min_rounds = 3
        self.sabotage = False

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
    if session.round < session.min_rounds:
        return None
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

        alive_names = [p.name for p in alive(session)]
        dead_names = [p.name for p in session.players.values() if p.dead]

        context = f"""
Живые: {alive_names}
Мёртвые: {dead_names}
История: {session.history[-5:]}
Есть скрытый предатель. Усиль напряжение.
"""

        data = await safe_generate(context)
        session.history.append(data["situation"])

        await bot.send_message(session.chat_id, f"Раунд {session.round}\n{data['situation']}")

        session.choices = {}
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=o, callback_data=f"choice_{i}")]
            for i, o in enumerate(data["options"])
        ])

        for p in alive(session):
            try:
                await bot.send_message(p.id, "Действие:", reply_markup=kb)
            except Exception:
                pass

        # Ждём, пока все сделают выбор (до 30 секунд)
        for _ in range(30):
            if len(session.choices) >= len(alive(session)):
                break
            await asyncio.sleep(1)

        chaos = 0
        for uid, choice in session.choices.items():
            player = session.players[uid]
            if player.role == "Предатель":
                chaos += 2
                player.suspicion += random.randint(0, 1)
            else:
                chaos += random.randint(0, 1)
                player.suspicion += random.randint(0, 2)

        session.history.append(f"хаос:{chaos}")

        await bot.send_message(session.chat_id, "Обсуждение 20 сек")
        await asyncio.sleep(20)

        session.votes = {}

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=p.name, callback_data=f"vote_{p.id}")]
            for p in alive(session)
        ])

        for p in alive(session):
            try:
                await bot.send_message(p.id, "Голосуй:", reply_markup=kb)
            except Exception:
                pass

        # Ждём, пока все проголосуют (до 25 секунд)
        for _ in range(25):
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
            text += "\nКазнён: " + session.players[killed].name

        await bot.send_message(session.chat_id, text)

        # Сброс ночных действий и саботажа перед новой ночью
        session.kill_target = None
        session.heal_target = None
        session.check_target = None
        session.sabotage = False

        # Ночные действия ролей (Предатель, Врач, Детектив)
        for p in alive(session):
            if p.role == "Предатель":
                targets = [pl for pl in alive(session) if pl.id != p.id]
                kb_night_kill = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"kill_{t.id}")]
                    for t in targets
                ] + [
                    [InlineKeyboardButton(text="Саботаж", callback_data="sabotage")]
                ])
                try:
                    await bot.send_message(p.id, "Действие:", reply_markup=kb_night_kill)
                except Exception:
                    pass

            if p.role == "Врач":
                kb_night_heal = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"heal_{t.id}")]
                    for t in alive(session)
                ])
                try:
                    await bot.send_message(p.id, "Лечение:", reply_markup=kb_night_heal)
                except Exception:
                    pass

            if p.role == "Детектив":
                targets_check = [pl for pl in alive(session) if pl.id != p.id]
                kb_night_check = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=t.name, callback_data=f"check_{t.id}")]
                    for t in targets_check
                ])
                try:
                    await bot.send_message(p.id, "Проверка:", reply_markup=kb_night_check)
                except Exception:
                    pass

        await asyncio.sleep(20)

        # Результат проверки детектива (если была)
        try:
            if session.check_target is not None:
                role_checked_player = session.players[session.check_target].role
                detective_user_id = next((p.id for p in session.players.values() if p.role == "Детектив"), None)
                if detective_user_id is not None and detective_user_id in session.players:
                    try:
                        await bot.send_message(detective_user_id, f"Роль: {role_checked_player}")
                    except Exception:
                        pass
        except Exception as e:
            logging.error(f"Ошибка при проверке роли: {e}")
        
         # Сообщение о саботаже (если был)
         if session.sabotage:
             await bot.send_message(session.chat_id, "💣 Саботаж усиливает хаос")
 
         # Результат ночного убийства и лечения (если были выбраны цели)
         if session.kill_target and session.kill_target != session.heal_target:
             session.players[session.kill_target].dead = True
             await bot.send_message(
                 session.chat_id,
                 f"🌑 Ночью убит {session.players[session.kill_target].name}"
             )
         else:
             await bot.send_message(session.chat_id, "🌙 Ночью никто не умер")
 
         # Подозрение (по уровню хаоса/подозрительности)
         suspects_sorted_by_suspicion_level_descending_order=sorted(alive(session), key=lambda x: x.suspicion, reverse=True)
         if suspects_sorted_by_suspicion_level_descending_order :
             most_suspicious_player_name=suspects_sorted_by_suspicion_level_descending_order[0].name 
             await bot.send_message(
                 session.chat_id,
                 f"🔍 Подозрение падает на: {most_suspicious_player_name}"
             )
 
         # Проверка на победу (если условия выполнены)
         win_result=win_check(session)
         if win_result is not None :
             await bot.send_message(
                 session.chat_id,
                 f"🏁 {win_result}"
             )
             session.started=False # Останавливаем игру при победе одной из сторон.
             break # Выходим из цикла игры.
