import aiohttp
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram import Router, F
from config import OPENDOTA_API
from db import add_link, get_links, add_name, del_link
from api import extract_steam32id, fetch
from view import build_profile_text, build_view
from keyboards import profile_keyboard, ViewCB, skip_keyboard, me_keyboard, UnlinkCB, unlink_keyboard


# ---------- fsm  ----------
class DotaProfile(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_link = State()
    waiting_for_name = State()

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
async def cmd_link(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Для привязки профиля отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_link)

# ---------- /me ----------
@router.message(Command("me"))
async def cmd_me(message: Message, state: FSMContext):
    await state.clear()
    idnames = await get_links(message.from_user.id)
    if not idnames:
        await message.answer("Вы еще не привязали аккаунт!\nДля привязки воспользуйтесь командой /link")
    else:
        await message.answer("Выберите аккаунт:", reply_markup=me_keyboard(idnames))

# ---------- /unlink ----------
@router.message(Command("unlink"))
async def unlink(message: Message, state: FSMContext):
    await state.clear()
    idnames = await get_links(message.from_user.id)
    if not idnames:
        await message.answer("Вы еще не привязали аккаунт!\nДля привязки воспользуйтесь командой /link")
    else:
        await message.answer("Выберите аккаунт для отвязки:", reply_markup=unlink_keyboard(idnames))

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
    await wait_msg.edit_text(final_text, parse_mode="HTML", reply_markup=profile_keyboard(steam_id, active="profile"))
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
        await state.update_data(steam_id=steam_id)
        await state.set_state(DotaProfile.waiting_for_name)
        await message.answer("Введите имя: ", reply_markup=skip_keyboard())
        return
    else:
        await wait_msg.edit_text("Вы уже привязали этот аккаунт.")
        return

# ---------- кнопка профиль ----------
@router.callback_query(ViewCB.filter())
async def stats_button(callback: CallbackQuery, callback_data: ViewCB, session: aiohttp.ClientSession):
    text = await build_view(steam_id=callback_data.steam_id, action=callback_data.action, session=session)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=profile_keyboard(callback_data.steam_id, active=callback_data.action))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()

# ---------- привязка имени к steam аккаунту ----------
@router.message(DotaProfile.waiting_for_name)
async def naming(message: Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "Слишком длинный текст или не тот формат сообщения.\n"
            "Отправьте имя текстом!"
        )
        return

    text = message.text.strip()

    if not (1 <= len(text) <= 16):
        await message.answer("❌ Длина текста должна быть от 1 до 16 символов.")
        return

    data = await state.get_data()
    steam_id = data["steam_id"]

    await add_name(message.from_user.id,steam_id, text)
    await message.answer("✅ Имя успешно привязано к аккаунту.")
    await state.clear()

# ---------- кнопка скипа при привязке имени ----------
@router.callback_query(DotaProfile.waiting_for_name, F.data == "skip_name")
async def skip_name(callback: CallbackQuery, state: FSMContext):
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Название не задано!\n"
                                         "На кнопках будет отображаться Steam ID аккаунта.")
    await state.clear()
    await callback.answer()

# ---------- кнопка отвязки ----------
@router.callback_query(UnlinkCB.filter())
async def unlink_button(callback: CallbackQuery, callback_data: UnlinkCB):
    if not isinstance(callback.message, Message):
        await callback.answer(
            "Сообщение устарело, отправьте команду заново.",
            show_alert=True
        )
        return

    deleted = await del_link(callback.from_user.id, callback_data.steam_id)
    idnames = await get_links(callback.from_user.id)
    status = "Успешно отвязано!" if deleted else "Аккаунт не привязан."

    if idnames:
        text = f"{status}\n\nВыберите следующий аккаунт для отвязки:"
        markup = unlink_keyboard(idnames)
    else:
        text = f"{status}\n\nПривязанных аккаунтов больше нет. Чтобы добавить новые, используйте /link"
        markup = None

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()

@router.message(Command("privet"))
async def privet(message: Message):
    await message.answer("⛓️Привет Дашенька))) ето я зхскурсед🩸🩸🩸 1000-7 ебать))... хех.. ода... я такой загадочный)) ⛓𓌹*♰*𓌺⛓ Желаю счастья здоровья и всего хорошего)))⛓️")