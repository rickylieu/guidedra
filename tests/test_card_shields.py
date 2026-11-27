import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
_spec = importlib.util.spec_from_file_location("make_card_shields", ROOT / "tools" / "make_card_shields.py")
mcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcs)


def skills(*entries):
    out = [None] * 10
    for entry in entries:
        out[entry["id"]] = entry
    return out


def one(skill_type, params):
    return mcs.leader_shields(1, skills({"id": 1, "type": skill_type, "params": params}))


def test_container_reaches_shield_sub_skill():
    data = skills(
        {"id": 1, "type": 138, "params": [2, 3]},
        {"id": 2, "type": 178, "params": [12, 8, 0, 130, 0, 130]},
        {"id": 3, "type": 171, "params": [8, 8, 0, 0, 2, 6000, 75]},
    )
    assert mcs.leader_shields(1, data) == [{"pct": 75}]


def test_conditional_shields():
    assert one(182, [16, 9, 4500, 81]) == [{"pct": 81}]
    assert one(169, [8, 800, 80]) == [{"pct": 80}]
    assert one(271, [1, 10000, 0, 3, 20000000, 300]) == []


def test_enemy_attribute_shields():
    assert one(129, [0, 32, 0, 150, 0, 8, 60]) == [{"pct": 60, "enemy": ["Light"]}]
    assert one(129, [8, 0, 280, 0, 280]) == []
    assert one(17, [0, 30]) == [{"pct": 30, "enemy": ["Fire"]}]
    assert one(36, [0, 2, 30]) == [{"pct": 30, "enemy": ["Fire", "Wood"]}]


def test_hp_threshold_shields():
    assert one(38, [50, 100, 50]) == [{"pct": 50, "hp_at_most": 50}]
    assert one(38, [100, 100, 80]) == [{"pct": 80, "hp_at_least": 100}]
    assert one(43, [100, 100, 20]) == [{"pct": 20, "hp_at_least": 100}]
    assert one(130, [99, 0, 0, 0, 0, 31, 50]) == [{"pct": 50, "hp_at_most": 99}]
    assert one(131, [50, 0, 0, 0, 0, 31, 50]) == [{"pct": 50, "hp_at_least": 50}]
    assert one(131, [50, 0, 256, 250]) == []
    assert one(183, [31, 0, 50, 400, 35]) == [{"pct": 35, "hp_at_least": 50}]


def test_lemocks_in_published_file():
    path = ROOT / "site" / "data" / "card_shields.json"
    if not path.exists():
        pytest.skip("card_shields.json not generated")
    assert json.loads(path.read_text(encoding="utf-8"))["10981"] == [{"pct": 75}]


def test_more_shield_types():
    assert one(285, [2, 6000, 50, 2]) == [{"pct": 50}]
    assert one(285, [16, 0, 83, 5]) == [{"pct": 83}]
    assert one(198, [50000, 1000, 50, 9999]) == [{"pct": 50}]
    assert one(198, [40000, 0, 50]) == [{"pct": 50}]
    assert one(163, [0, 0, 0, 0, 0, 31, 20]) == [{"pct": 20}]
    assert one(163, []) == []
    assert one(235, [17, 0, 6, 300, 10, 2, 1]) == [{"pct": 10}]
    assert one(235, [17, 0, 5, 200]) == []
    assert one(129, [0, 0, 0, 0, 0, 31, 40]) == [{"pct": 40}]


def test_cross_match_shield():
    assert one(210, [2, 35, 3]) == [{"pct": 35}]
    assert one(210, [24, 20, 2]) == [{"pct": 20}]
