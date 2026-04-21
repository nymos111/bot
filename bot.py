import asyncio
import os
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from states import Onboarding, Main
from db import init_db, save_user, save_message, get_last_messages
from logic import extract_signals, update_interest, update_stage, analyze_context, generate_replies

load_dotenv()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

gender_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Парень"), KeyboardButton(text="Девушка")]],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await message.answer("Твой пол?", reply_markup=gender_kb)
    await state.set_state(Onboarding.gender)

@dp.message(Onboarding.gender)
async def gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await message.answer("Пол собеседника?", reply_markup=gender_kb)
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

    replies = generate_replies(stage, context, history)

    await message.answer(
        f"Интерес: {interest}\n"
        f"Стадия: {stage}\n"
        f"Динамика: {context['momentum']}\n\n"
        f"{replies['light']}\n\n"
        f"{replies['confident']}\n\n"
        f"{replies['flirt']}"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
