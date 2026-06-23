from aiogram.fsm.state import State, StatesGroup


class PostStates(StatesGroup):
    waiting_post = State()
    editing_caption = State()
    waiting_copy_caption = State()


class AdminStates(StatesGroup):
    waiting_admin_id = State()
