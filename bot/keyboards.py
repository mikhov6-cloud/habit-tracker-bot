from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Today"), KeyboardButton(text="📊 Stats")],
            [KeyboardButton(text="📋 Habits"), KeyboardButton(text="❓ Help")],
        ],
        resize_keyboard=True,
    )
