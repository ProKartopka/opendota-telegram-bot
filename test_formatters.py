import pytest

from formatters import format_matches, format_rank, format_heroes
from config import HEROES_DICT
import formatters

def normal_match(**changes):
    match = {
        "hero_id": 14,
        "kills": 17,
        "deaths": 3,
        "assists": 12,
        "duration": 2400,
        "player_slot": 3,
        "radiant_win": False,
    }
    match.update(changes)
    return match


@pytest.fixture(autouse=True)
def mock_heroes(monkeypatch):
    monkeypatch.setitem(HEROES_DICT, "14", "Pudge")


@pytest.mark.parametrize(
    ("rank_tier", "expected"),
    [
        pytest.param(None, "Калибровка", id="none"),
        pytest.param(0, "Калибровка", id="zero"),
        pytest.param(53, "Легенда 3", id="legend_3"),
        pytest.param(80, "Титан", id="titan"),
        pytest.param(1241249, "Неизвестно", id="unknown"),
    ],
)
def test_format_rank(rank_tier, expected):
    assert format_rank(rank_tier) == expected


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        pytest.param({"radiant_win": True}, "Победа", id="radiant_true"),
        pytest.param({}, "Поражение", id="radiant_false"),
        pytest.param({"player_slot": 130, "radiant_win": True}, "Поражение", id="dire_true"),
        pytest.param({"player_slot": 130}, "Победа", id="dire_false"),
        pytest.param({"player_slot": 130, "radiant_win": None}, "Неизвестно", id="radiant_win_none"),
    ],
)
def test_format_matches_outcome(changes, expected):
    data = [normal_match(**changes)]
    result = format_matches(data)
    assert expected in result


def test_format_matches_empty():
    assert format_matches([]) is None


def make_hero(**changes):
    hero = {
        "hero_id": 14,
        "games": 20,
        "win": 10
    }
    hero.update(changes)
    return hero

def test_format_heroes_epmty_or_below_win(monkeypatch):
    monkeypatch.setattr("formatters.MIN_GAMES", 5)
    assert format_heroes([]) is None
    assert format_heroes([make_hero(games=5)]) is None

def test_format_heroes_sort_limit_and_winrate(monkeypatch):
    monkeypatch.setattr("formatters.MIN_GAMES", 5)
    monkeypatch.setattr("formatters.TOP_HEROES", 2)
    monkeypatch.setitem(formatters.HEROES_DICT, "14", "Pudge")

    data = [
        make_hero(hero_id=14, games=25, win=5),
        make_hero(hero_id=99, games=30, win=10),
        make_hero(hero_id=1, games=20, win=10),
        make_hero(hero_id=2, games=3, win=3),
    ]

    result = format_heroes(data)
    lines = result.splitlines()

    assert len(lines) == 2
    assert lines[0] == "• Герой 99: 30 игр (33.3%)"
    assert lines[1] == "• Pudge: 25 игр (20.0%)"