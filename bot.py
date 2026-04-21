import asyncio
import os
import logging
import random
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from states import Onboarding, Main
from db import init_db, save_user, save_message, get_last_messages
from logic import extract_signals, update_interest, update_stage, analyze_context, generate_replies
from ai import humanize_with_ai

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Парень"), KeyboardButton(text="Девушка")]],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer("Твой пол?", reply_markup=kb)
    await state.set_state(Onboarding.gender)

@dp.message(Onboarding.gender)
async def gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await message.answer("Пол собеседника?", reply_markup=kb)
    await state.set_state(Onboarding.target_gender)

@dp.message(Onboarding.target_gender)
async def target(message: types.Message, state: FSMContext):
    await state.update_data(target_gender=message.text)
    await message.answer("Где общаетесь?")
    await state.set_state(Onboarding.platform)

@dp.message(Onboarding.platform)
async def platform(message: types.Message, state: FSMContext):
    await state.update_data(platform=message.text)
    await message.answer("Цель общения?")
    await state.set_state(Onboarding.goal)

@dp.message(Onboarding.goal)
async def goal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data["goal"] = message.text

    await save_user(message.from_user.id, data)

    await message.answer("Отправь сообщение собеседника")
    await state.set_state(Main.waiting_message)

@dp.message(Main.waiting_message)
async def analyze(message: types.Message):
    user_id = message.from_user.id

    await save_message(user_id, message.text)
    history = await get_last_messages(user_id)

    signals = extract_signals(message.text)
    interest, _ = update_interest(50, signals)
    stage = update_stage(interest)
    context = analyze_context(history)

    base_replies = generate_replies(stage, context)

    final_replies = []
    for text in base_replies:
        if random.random() < 0.5:
            text = await humanize_with_ai(text)
        final_replies.append(text)

    await message.answer(
        f"Интерес: {interest}\n"
        f"Стадия: {stage}\n"
        f"Динамика: {context['momentum']}\n\n"
        f"1. {final_replies[0]}\n\n"
        f"2. {final_replies[1]}\n\n"
        f"3. {final_replies[2]}"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
