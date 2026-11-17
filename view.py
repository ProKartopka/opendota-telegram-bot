import aiohttp
from html import escape
from config import OPENDOTA_API, MIN_GAMES, log
from api import fetch
from formatters import format_matches, format_rank, format_heroes

# ---------- текст/вн. вид кнопок ----------
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

