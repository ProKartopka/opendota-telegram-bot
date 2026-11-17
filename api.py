import aiohttp, asyncio, re
from config import log, STEAM_API_KEY, STEAM64_OFFSET, OPENDOTA_API, HEROES_DICT


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