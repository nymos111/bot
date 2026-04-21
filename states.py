from aiogram.fsm.state import StatesGroup, State

class Onboarding(StatesGroup):
    gender = State()
    target_gender = State()
    platform = State()
    goal = State()

class Main(StatesGroup):
    waiting_message = State()
