from config import MEDALS, MIN_GAMES, TOP_HEROES, HEROES_DICT, RECENT_MATCHES
from html import escape

# ---------- форматирование текста----------
def format_rank(rank_tier) -> str:
    if not rank_tier:
        return "Калибровка"
    medal_id, stars = divmod(rank_tier, 10)
    medal_name = MEDALS.get(medal_id, "Неизвестно")
    if medal_id == 8:  # у Титана звёзд нет
        return medal_name
    return f"{medal_name} {stars}"

def format_heroes(data_player_heroes) -> str | None:
    if not data_player_heroes:
        return None

    played = [h for h in data_player_heroes if h.get("games", 0) > MIN_GAMES]
    if not played:
        return None

    played.sort(key=lambda h: h["games"], reverse=True)

    lines = []
    for hero in played[:TOP_HEROES]:
        games = hero["games"]
        wins = hero.get("win", 0)
        winrate = round(wins / games * 100, 1)
        hero_id = str(hero.get("hero_id"))
        hero_name = HEROES_DICT.get(hero_id, f"Герой {hero_id}")
        lines.append(f"• {escape(hero_name)}: {games} игр ({winrate}%)")
    return "\n".join(lines)

def format_matches(data_matches) -> str | None:
    if not data_matches:
        return None

    lines = []
    for match in data_matches[:RECENT_MATCHES]:
        hero_id = str(match.get("hero_id"))
        hero_name = HEROES_DICT.get(hero_id, f"Герой {hero_id}")
        kills = match.get("kills", 0)
        deaths = match.get("deaths", 0)
        assists = match.get("assists", 0)
        minutes, seconds = divmod(match.get("duration", 0), 60)
        is_radiant = match.get("player_slot", 0) < 128
        radiant_win = bool(match.get("radiant_win"))
        win = "✅ Победа" if is_radiant == radiant_win else "❌ Поражение"
        lines.append(f"<b>{win}</b>: {escape(hero_name)} - {kills}/{deaths}/{assists} • {minutes}:{seconds:02d}\n")
    return "\n".join(lines)
