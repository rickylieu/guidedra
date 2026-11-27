import json
from pathlib import Path

import pytest

DATA = Path(__file__).parents[1] / "site" / "data"


def dungeon_files():
    return [p for p in DATA.glob("*.json") if p.name not in {"index.json", "card_elements.json"}]


def test_no_in_order_action_labels():
    for path in dungeon_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        for floor in data.get("floors", []):
            for tag in floor.get("tags", []):
                for variant in tag.get("variants") or []:
                    assert not str(variant.get("when", "")).startswith("In-order action"), (
                        path.name, floor["label"], tag["name"], variant["when"])


def test_floor14_attribute_absorb_consolidates():
    path = DATA / "tenkyu-challenge.json"
    if not path.exists():
        pytest.skip("tenkyu-challenge.json not built")
    data = json.loads(path.read_text(encoding="utf-8"))
    floor = next(f for f in data["floors"] if f["label"] == "Floor 14")
    tag = next(t for t in floor["tags"] if t["name"] == "Attribute absorb")
    variants = tag.get("variants") or []
    assert [v["when"] for v in variants] == ["Action 7"]
    assert {"AppMedia", "GameWith"} <= set(variants[0]["sources"])
