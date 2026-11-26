import json
from pathlib import Path

from glossary import is_critical

DATA = Path(__file__).parents[1] / "site" / "data"


def test_enemy_shield_is_critical():
    assert is_critical("Enemy shield")


def test_shield_floors_listed_in_summary():
    for path in DATA.glob("*.json"):
        if path.name in {"index.json", "card_elements.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        listed = data.get("summary", {}).get("Enemy shield", [])
        for floor in data.get("floors", []):
            if any(tag["name"] == "Enemy shield" for tag in floor["tags"]):
                assert floor["label"] in listed, (path.name, floor["label"])
