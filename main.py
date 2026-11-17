import asyncio, aiohttp

from html import escape
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from db import init_db, add_link

from config import OPENDOTA_API, MIN_GAMES, HTTP_HEADERS, BOT_TOKEN, STEAM_API_KEY, log
from formatters import format_rank, format_heroes, format_matches
from api import fetch, extract_steam32id, load_heroes
from keyboards import view_keyboard, ViewCB

# ---------- env check ----------
if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN в .env")
if not STEAM_API_KEY:
    log.warning("STEAM_API_KEY не задан: ссылки вида steamcommunity.com/id/... работать не будут")

# ---------- основа бота ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

class DotaProfile(StatesGroup):
    waiting_for_steam_id = State()
    waiting_for_link = State()

# ---------- форматирование ----------
async def build_profile_text(session: aiohttp.ClientSession, steam_id: str):
    data_profile = await fetch(session, f"{OPENDOTA_API}/players/{steam_id}")
    if not data_profile or not data_profile.get("profile"):
        return

    name = data_profile["profile"].get("personaname") or "Неизвестный игрок"
    mmr_estimate = data_profile.get("mmr_estimate")
    rank_text = format_rank(data_profile.get("rank_tier"))

    if isinstance(mmr_estimate, dict) and mmr_estimate.get("estimate"):
        mmr = mmr_estimate["estimate"]
    else:
        mmr = "Скрыт"

    final_text = (
        "<b>Профиль Dota 2</b>\n\n"
        f"👤 Игрок: {escape(name)}\n"
        f"🔢 MMR: {escape(str(mmr))}\n"
        f"🌟 Ранг: {escape(rank_text)}\n"
    )
    return final_text

async def build_view(action: str, steam_id: str, session: aiohttp.ClientSession):
    # --- ВКЛАДКА ПРОФИЛЯ ---
    if action == "profile":
        profile_info = await build_profile_text(session, steam_id)
        if profile_info:
            return profile_info
        else:
            return "Профиль не найден или скрыт."
    # --- ВКЛАДКА ГЕРОЕВ ---
    elif action == "heroes":
        data_player_heroes = await fetch(session, f"{OPENDOTA_API}/players/{steam_id}/heroes")
        heroes_text = format_heroes(data_player_heroes)
        if heroes_text:
            heroes_info = (
            "🧙‍♀️ <b>Сигнатурные герои:</b>\n\n"
            f"{heroes_text}"
        )
            return heroes_info
        else:
            return f"Не удалось получить статистику или нет героев с более чем {MIN_GAMES} играми."
    # --- ВКЛАДКА МАТЧЕЙ ---
    elif action == "matches":
        data_matches = await fetch(session, f"{OPENDOTA_API}/players/{steam_id}/recentMatches")
        matches_text = format_matches(data_matches)
        if matches_text:
            matches_info = (
            "<b>Последние матчи:</b>\n\n"
            f"{matches_text}"
        )
            return matches_info
        else:
            return f"Не удалось получить статистику."
    return log.error("Выбрана неверная вкладка!")


# ---------- хендлеры ----------
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я бот для сбора статистики Dota 2.\n"
        "Отправь команду /stats, чтобы посмотреть профиль и любимых героев."
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_steam_id)

@router.message(Command("link"))
async def link(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Для привязки профиля отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_link)

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

@router.callback_query(ViewCB.filter())
async def stats_button(callback: CallbackQuery, callback_data: ViewCB, session: aiohttp.ClientSession):
    text = await build_view(steam_id=callback_data.steam_id, action=callback_data.action, session=session)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=view_keyboard(callback_data.steam_id, active=callback_data.action))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()

# ---------- запуск ----------



async def main():
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(headers=HTTP_HEADERS, timeout=timeout) as session:
        await load_heroes(session)
        await init_db()
        dp["session"] = session  # доступна в хендлерах как аргумент session
        log.info("Бот запущен!")
        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Остановлено пользователем")