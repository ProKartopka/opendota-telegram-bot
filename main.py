import asyncio, aiohttp
from aiogram import Bot, Dispatcher
from db import init_db
from config import HTTP_HEADERS, BOT_TOKEN, STEAM_API_KEY, log
from api import load_heroes
from handlers import router

# ---------- env check ----------
if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN в .env")
if not STEAM_API_KEY:
    log.warning("STEAM_API_KEY не задан: ссылки вида steamcommunity.com/id/... работать не будут")

# ---------- основа бота ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

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