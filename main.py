import re
import asyncio
import aiohttp

from html import escape
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from db import init_db, add_link

from config import STEAM64_OFFSET, OPENDOTA_API, MIN_GAMES, TOP_HEROES, RECENT_MATCHES, HTTP_HEADERS, HEROES_DICT, MEDALS, BOT_TOKEN, STEAM_API_KEY, log
from formatters import format_rank, format_heroes, format_matches

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

class ViewCB(CallbackData, prefix="me"):
    action: str
    steam_id: str

# ---------- работа с API ----------
async def fetch(session: aiohttp.ClientSession, url: str, params: dict | None = None):
    """Универсальный GET-запрос, возвращает JSON или None."""
    try:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            log.warning("API %s вернул код %s", url, response.status)
            return None
    except Exception as e:
        log.error("Ошибка соединения с %s: %s", url, e)
        return None


async def resolve_vanity_url(session: aiohttp.ClientSession, vanity_name: str):
    """Превращает кастомный steam-ник в Steam64ID."""
    if not STEAM_API_KEY:
        return None
    data = await fetch(
        session,
        "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/",
        params={"key": STEAM_API_KEY, "vanityurl": vanity_name},
    )
    if data and data.get("response", {}).get("success") == 1:
        return int(data["response"]["steamid"])
    return None


async def extract_steam32id(text: str, session: aiohttp.ClientSession):
    """Достаёт Steam32ID из ссылки Dotabuff/Steam, Steam64ID или Steam32ID."""
    match_db = re.search(r"dotabuff\.com/players/(\d+)", text)
    if match_db:
        return match_db.group(1)

    raw_id = None

    match_steam_number = re.search(r"steamcommunity\.com/profiles/(\d+)", text)
    if match_steam_number:
        raw_id = int(match_steam_number.group(1))
    else:
        match_steam_custom = re.search(r"steamcommunity\.com/id/([^/?#\s]+)", text)
        if match_steam_custom:
            raw_id = await resolve_vanity_url(session, match_steam_custom.group(1))
        elif text.isdigit():
            raw_id = int(text)

    if not raw_id:
        return None
    if raw_id > STEAM64_OFFSET:
        return str(raw_id - STEAM64_OFFSET)
    return str(raw_id)

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

def view_keyboard(steam_id: str, active: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for section, title in (("profile", "Профиль"), ("heroes", "Сигнатурные герои"), ("matches", "Последние матчи")):
        label = f"• {title}" if section == active else title
        builder.button(text=label, callback_data=ViewCB(action=section, steam_id=steam_id))
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="DotaBuff", url=f"https://www.dotabuff.com/players/{steam_id}"))
    return builder.as_markup()
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
async def load_heroes(session: aiohttp.ClientSession, attempts: int = 3) -> bool:
#   Загружает список героев с повторными попытками.
    log.info("Загружаю базу героев из OpenDota...")
    for attempt in range(1, attempts + 1):
        heroes_list = await fetch(session, f"{OPENDOTA_API}/heroes")
        if heroes_list:
            for hero in heroes_list:
                HEROES_DICT[str(hero["id"])] = hero["localized_name"]
            log.info("Успешно! Загружено %d героев.", len(HEROES_DICT))
            return True
        log.warning("Попытка %d/%d не удалась", attempt, attempts)
        await asyncio.sleep(2 * attempt)
    log.error("Не удалось загрузить героев, будут показаны ID")
    return False


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