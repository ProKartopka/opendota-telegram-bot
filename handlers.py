import aiohttp
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram import Router
from config import OPENDOTA_API
from db import add_link
from api import extract_steam32id, fetch
from view import build_profile_text, build_view
from keyboards import view_keyboard, ViewCB

# ---------- fsm  ----------
class DotaProfile(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_link = State()

router = Router()


# ---------- хендлеры ----------
# !!! КОМАНДЫ ВЫШЕ ХЕНДЛЕРОВ СОСТОЯНИЙ !!!

# ---------- /start ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я бот для сбора статистики Dota 2.\n"
        "Отправь команду /stats, чтобы посмотреть профиль и любимых героев."
    )

# ---------- /stats ----------
@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_steam_id)

# ---------- /link ----------
@router.message(Command("link"))
async def link(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Для привязки профиля отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_link)

# ---------- ответ после /stats ----------
@router.message(DotaProfile.waiting_for_steam_id)
async def process_steam_id(message: Message, state: FSMContext, session: aiohttp.ClientSession):
    if not message.text:
        await message.answer(
            "❌ Не удалось распознать ID.\n"
            "Отправьте цифры, ссылку на Steam или Dotabuff."
        )
        return None # состояние сохраняем, чтобы можно было попробовать ещё раз

    wait_msg = await message.answer("Ищу профиль, секунду...")
    text = message.text.strip()

    steam_id = await extract_steam32id(text, session)
    if not steam_id:
        await wait_msg.edit_text(
            "❌ Не удалось распознать ID.\n"
            "Отправьте цифры, ссылку на Steam или Dotabuff."
        )
        return None  # состояние сохраняем, чтобы можно было попробовать ещё раз

    final_text = await build_profile_text(session, steam_id)
    if not final_text:
        await wait_msg.edit_text("Профиль не найден или скрыт.")
        return
    await wait_msg.edit_text(final_text, parse_mode="HTML", reply_markup=view_keyboard(steam_id, active="profile"))
    await state.clear()

# ---------- привязка ----------
@router.message(DotaProfile.waiting_for_link)
async def linking(message: Message, state: FSMContext, session: aiohttp.ClientSession):
    if not message.text:
        await message.answer(
            "❌ Не удалось распознать ID.\n"
            "Отправьте цифры, ссылку на Steam или Dotabuff."
        )
        return
    text = message.text.strip()

    wait_msg = await message.answer("Ищу профиль, секунду...")

    steam_id = await extract_steam32id(text, session)
    if not steam_id:
        await wait_msg.edit_text(
            "❌ Не удалось распознать ID.\n"
            "Отправьте цифры, ссылку на Steam или Dotabuff."
        )
        return  # состояние сохраняем, чтобы можно было попробовать ещё раз

    data_profile = await fetch(session, f"{OPENDOTA_API}/players/{steam_id}")

    if not data_profile or not data_profile.get("profile"):
        await wait_msg.edit_text("Профиль не найден или скрыт.")
        return # состояние сохраняем, чтобы можно было попробовать ещё раз
    if await add_link(message.from_user.id, steam_id):
        await wait_msg.edit_text("✅ Аккаунт успешно привязан.")
    else:
        await wait_msg.edit_text("Вы уже привязали этот аккаунт.")
        return

    await state.clear()

# ---------- кнопка в профиле ----------
@router.callback_query(ViewCB.filter())
async def stats_button(callback: CallbackQuery, callback_data: ViewCB, session: aiohttp.ClientSession):
    text = await build_view(steam_id=callback_data.steam_id, action=callback_data.action, session=session)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=view_keyboard(callback_data.steam_id, active=callback_data.action))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()
