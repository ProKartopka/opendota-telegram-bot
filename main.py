import os
import asyncio
import aiohttp
import re

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext


#env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

#основа бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

HEROES_DICT = {}

class DotaProfile(StatesGroup):
    waiting_for_steam_id = State()

# Вытаскиваем Steam32ID из ссылки на с кастомным (буквенным) айди
async def resolve_vanity_url(session, vanity_name):
    url = f"https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={vanity_name}"
    async with session.get(url) as response:
        if response.status == 200:
            data = await response.json()
            if data.get("response", {}).get("success") == 1:
                return int(data["response"]["steamid"])
    return None

# Вытаскиваем Steam32ID из ссылки на DotaBuff, Steam64ID, Steam32ID
async def extract_steam32ID(text: str, session: aiohttp.ClientSession):
    match_db = re.search(r'dotabuff\.com/players/(\d+)', text)
    if match_db:
        return match_db.group(1)

    raw_id = None

    match_steam_number = re.search(r'steamcommunity\.com/profiles/(\d+)', text)
    if match_steam_number:
        raw_id = int(match_steam_number.group(1))

    match_steam_custom = re.search(r'steamcommunity\.com/id/([^/]+)', text)
    if match_steam_custom:
        vanity_name = match_steam_custom.group(1)
        raw_id = await resolve_vanity_url(session, vanity_name)

    if not raw_id and text.isdigit():
        raw_id = int(text)

    if raw_id:
        if raw_id > 76561197960265728:
            return str(raw_id - 76561197960265728)
        return str(raw_id)

    return None

# Универсальная функция для выполнения GET-запросов
async def fetch(session, url):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            print(f"Ошибка API: сервер вернул код {response.status}")
            return None
    except Exception as e:
        print(f"Ошибка соединения: {e}")
        return None

# Комманда /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот для сбора статистики Dota 2.\n"
        "Отправь команду /stats, чтобы проверить винрейты."
    )

# Комманда stats
@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    await message.answer("Отправьте цифры, ссылку на Steam или Dotabuff.")
    await state.set_state(DotaProfile.waiting_for_steam_id)

# Получение информации из OpenDota, ответ пользователю
@router.message(DotaProfile.waiting_for_steam_id)
async def process_steam_id(message: Message, state: FSMContext):
    wait_msg = await message.answer("Ищу профиль, секунду...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    async with aiohttp.ClientSession(headers=headers) as session:
        steamID = await extract_steam32ID(message.text, session)

    if not steamID:
        await message.answer(
            "❌ Не удалось распознать ID.\n"
            "Отправьте цифры, ссылку на Steam или Dotabuff."
        )
        return

    url_profile = f"https://api.opendota.com/api/players/{steamID}"
    url_player_heroes = f"https://api.opendota.com/api/players/{steamID}/heroes"

    async with aiohttp.ClientSession(headers=headers) as session:
        data_profile, data_player_heroes = await asyncio.gather(
            fetch(session, url_profile),
            fetch(session, url_player_heroes)
        )

        if not data_profile or not data_profile.get("profile"):
            await wait_msg.edit_text("Профиль не найден или скрыт.")
            await state.clear()
            return

        name = data_profile["profile"].get("personaname", "Неизвестный игрок")

        mmr_estimate =  data_profile.get("mmr_estimate")
        if isinstance(mmr_estimate, dict) and mmr_estimate.get("estimate"):
            mmr = mmr_estimate.get("estimate")
        else:
            mmr = "Скрыт"

        rank_tier = data_profile.get("rank_tier")
        if rank_tier:
            medal_id = rank_tier // 10
            stars = rank_tier % 10

            medals = {
                1: "Рекрут", 2: "Страж", 3: "Рыцарь", 4: "Герой",
                5: "Легенда", 6: "Властелин", 7: "Божество", 8: "Титан"
            }
            medal_name = medals.get(medal_id)

            rank_text = medal_name if medal_id == 8 else f"{medal_name} {stars}"
        else:
            rank_text = "Калибровка"

        final_text = f"*Профиль Dota 2*\n\n👤Игрок: {name}\n🔢MMR: {mmr}\n🌟Ранг: {rank_text}🌟\n\n🧙‍♀️🧙‍♀️🧙‍♀️Сигнатурные герои: "

    if data_player_heroes:
        has_heroes = False
        for hero in data_player_heroes:
            games = hero.get("games", 0)
            wins = hero.get("win", 0)

            if games > 10:
                winrate = round((wins / games) * 100, 1) if games > 10 else 0
                if winrate > 40:
                    has_heroes = True
                    hero_id = str(hero.get("hero_id"))
                    hero_name = HEROES_DICT.get(hero_id, f"Герой: {hero_id}")
                    final_text += f"\n• {hero_name}: {games} игр ({winrate}%)"

        if not has_heroes:
            final_text += "\nНет героев с винрейтом выше 40%"
    else:
        final_text += "\nНе удалось получить статистику матчей."

    await wait_msg.edit_text(final_text, parse_mode="Markdown")
    await state.clear()

# Загрузка списка всех героев из сайта OpenDota
async def on_startup():
    print("Загружаю базу героев из OpenDota...")
    async with aiohttp.ClientSession() as session:
        heroes_list = await fetch(session, "https://api.opendota.com/api/heroes")
        if heroes_list:
            for hero in heroes_list:
                HEROES_DICT[str(hero["id"])] = hero["localized_name"]
            print(f"Успешно! Загружено {len(HEROES_DICT)} героев.")
        else:
            print("Ошибка: не удалось загрузить героев при старте")

async def main():
    await on_startup()
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())