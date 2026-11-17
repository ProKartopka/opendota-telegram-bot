from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---------- кнопки ----------
class ViewCB(CallbackData, prefix="me"):
    action: str
    steam_id: str

def profile_keyboard(steam_id: str, active: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section, title in (("profile", "Профиль"), ("heroes", "Сигнатурные герои"), ("matches", "Последние матчи")):
        label = f"• {title}" if section == active else title
        builder.button(text=label, callback_data=ViewCB(action=section, steam_id=steam_id))
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="DotaBuff", url=f"https://www.dotabuff.com/players/{steam_id}"))
    return builder.as_markup()

def me_keyboard(ids: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for steam_id in ids:
        builder.button(text=f"{steam_id}", callback_data=ViewCB(action="profile", steam_id=steam_id))
    builder.adjust(1)
    return builder.as_markup()