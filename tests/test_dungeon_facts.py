import copy
import json
import re
from pathlib import Path

import pytest

from glossary import annotate_action, annotate_record, english_trait
from build import _publish_dungeon, _render_report
from merge import merge_dungeon
from parsers import altema, appmedia, game8, gamewith
from rules import floor_label


RAW_DIR = Path(__file__).parents[1] / "raw" / "tenkyu-challenge"


def _saved_record(source, parser):
    path = RAW_DIR / f"{source}.html"
    if not path.is_file():
        pytest.skip(f"saved {source} page is not available")
    return parser.parse(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def altema_record():
    return _saved_record("altema", altema)


@pytest.fixture(scope="module")
def appmedia_record():
    return _saved_record("appmedia", appmedia)


@pytest.fixture(scope="module")
def gamewith_record():
    return _saved_record("gamewith", gamewith)


@pytest.fixture(scope="module")
def game8_record():
    return _saved_record("game8", game8)


def _floor(record, number):
    return next(floor for floor in record["floors"] if floor["number"] == number)


def _enemy(record, card):
    return next(
        enemy
        for floor in record["floors"]
        for enemy in floor["enemies"]
        if enemy["card"] == card
    )


def _actions(record):
    return [
        action
        for floor in record["floors"]
        for enemy in floor["enemies"]
        for action in enemy["actions"]
    ]


def test_altema_tenkyu_facts(altema_record):
    record = annotate_record(altema_record)
    numbered = [floor for floor in record["floors"] if floor["number"] is not None]
    invade = next(floor for floor in record["floors"] if floor["number"] is None)

    assert len(numbered) == 15
    assert invade["invade_floors"] == [6, 8]
    assert _enemy(record, 10981)

    floor15 = _floor(record, 15)
    combo_absorb = [
        action
        for action in _actions({"floors": [floor15]})
        if "Combo absorb" in action["tags"]
    ]
    assert combo_absorb
    assert combo_absorb[0]["timing_kind"] == "on_super_resolve"
    assert "14 or fewer combos" in combo_absorb[0]["details"]


def test_gamewith_tenkyu_facts(gamewith_record):
    record = annotate_record(gamewith_record)
    numbered = [floor for floor in record["floors"] if floor["number"] is not None]
    invade = next(floor for floor in record["floors"] if floor["number"] is None)
    tenkyu_enemy = _enemy(record, 10981)

    assert len(numbered) == 15
    assert invade["invade_floors"] == [6, 8]
    assert tenkyu_enemy["hp"] == 650_000_000_000
    assert tenkyu_enemy["defense"] == 200_000_000
    assert tenkyu_enemy["parts"][0]["hp"] == 750_000_000_000

    floor15_enemy = _enemy(record, 14019)
    assert [part["hp"] for part in floor15_enemy["parts"]] == [
        3_200_000_000_000,
        3_700_000_000_000,
    ]
    hits = {action["hit"] for action in _actions(record) if action["hit"] is not None}
    assert 7_650_000 in hits
    assert 175_000_000 in hits
    assert all(isinstance(hit, int) for hit in hits)

    floor14_orders = {
        action["order"]
        for action in _actions({"floors": [_floor(record, 14)]})
        if action["order"] is not None
    }
    floor15_orders = {
        action["order"]
        for action in _actions({"floors": [_floor(record, 15)]})
        if action["order"] is not None
    }
    assert set(range(2, 8)) <= floor14_orders
    assert set(range(2, 7)) <= floor15_orders

    floor15_combo_absorb = [
        action
        for action in _actions({"floors": [_floor(record, 15)]})
        if "Combo absorb" in action["tags"]
    ]
    assert floor15_combo_absorb
    assert floor15_combo_absorb[0]["timing_kind"] == "on_super_resolve"
    assert "14 or fewer combos" in floor15_combo_absorb[0]["details"]


def test_gamewith_orb_icon_annotations(gamewith_record):
    record = annotate_record(gamewith_record)
    actions = _actions(record)

    attribute_absorb = next(
        action for action in actions if "[光][闇]吸収" in action["text_jp"]
    )
    assert "Attribute absorb" in attribute_absorb["tags"]
    assert "Light, Dark" in attribute_absorb["details"]

    unmatchable = next(
        action
        for action in actions
        if "[回復]" in action["text_jp"] and "消せない" in action["text_jp"]
    )
    assert "Unmatchable" in unmatchable["tags"]
    assert "Heart" in unmatchable["details"]

    bombs = next(action for action in actions if "[爆弾]を8個生成" in action["text_jp"])
    assert {"Bombs", "Orbs spawned"} <= set(bombs["tags"])
    assert "8 orbs" in bombs["details"]


def test_appmedia_super_resolve_header_does_not_change_action_timing(appmedia_record):
    record = annotate_record(appmedia_record)
    floor5 = _floor(record, 5)
    boss = _enemy({"floors": [floor5]}, 1103)

    assert "超根性:40%" in boss["traits_jp"]
    assert "Super resolve at 40%" in boss["traits"]
    absorb = next(
        action for action in boss["actions"] if "Damage absorb" in action["tags"]
    )
    assert absorb["when"] == "Preemptive"
    assert "5B or more" in absorb["details"]


def test_game8_tenkyu_facts(game8_record):
    record = annotate_record(game8_record)
    numbered = [floor for floor in record["floors"] if floor["number"] is not None]

    assert [floor["number"] for floor in numbered] == list(range(1, 16))
    assert [floor_label(floor) for floor in numbered] == [
        f"Floor {number}" for number in range(1, 16)
    ]
    assert all(
        "Combo absorb" not in action["tags"]
        for action in _actions(record)
    )

    manifest_path = Path(__file__).parents[1] / "dungeons.json"
    entry = json.loads(manifest_path.read_text(encoding="utf-8"))[0]
    entry.pop("primary", None)
    _, diagnostics = merge_dungeon(entry, {"game8": game8_record}, {})
    assert any(
        item["tag"] == "Combo absorb"
        for item in diagnostics["must_counter_misses"]
    )
    assert any(
        item["card"] is None and item["name_jp"]
        for item in diagnostics["unnamed_cards"]
    )


def test_published_json_has_no_japanese_outside_names():
    path = Path(__file__).parents[1] / "site" / "data" / "tenkyu-challenge.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    japanese = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

    def check(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "name_jp" or (key == "name" and len(path) >= 2 and path[-2] == "enemies"):
                    continue
                check(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                check(child, path + (index,))
        elif isinstance(value, str):
            assert not japanese.search(value), f"Japanese text outside allowed name fields at {path}: {value}"

    check(data)


def test_published_warning_details_and_hit_severity():
    path = Path(__file__).parents[1] / "site" / "data" / "tenkyu-challenge.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    floors = {floor["label"]: floor for floor in data["floors"]}

    def tag(label, name):
        return next(item for item in floors[label]["tags"] if item["name"] == name)

    assert "for 4 turns" in tag("Floor 1", "Skill delay")["details"]
    assert "for 5 turns" in tag("Floor 4", "Skill delay")["details"]
    assert "for 10 turns, 5B or more" in tag("Floor 2", "Damage void")["details"]
    assert "for 1 turn" in tag("Floor 2", "Unmatchable")["details"][0]
    assert "for 2 turns" in tag("Floor 10", "Unmatchable")["details"][0]
    combo_void_details = " ".join(tag("Floor 14", "Combo void")["details"])
    assert "12 or fewer combos" in combo_void_details
    assert "512 or fewer combos" not in combo_void_details
    assert "Void buffs" in {item["name"] for item in floors["Floor 3"]["tags"]}
    assert "Invulnerable" not in {item["name"] for item in floors["Floor 3"]["tags"]}
    assert "Invulnerable" not in data["summary"]
    assert "Skill-effect wipe" not in data["summary"]
    assert "Floor 3" not in data["summary"].get("Awoken bind", [])
    assert "Floor 3" not in data["summary"].get("Bind", [])
    assert "Light" in tag("Floor 15", "Full-board change")["details"][0]
    assert "Heart" in tag("Floor 5", "Full-board change")["details"][0]
    assert any("Water" in detail for detail in tag("Floor 10", "Full-board change")["details"])
    assert "Full-board change" not in {
        item["name"] for item in floors["Floor 3"]["tags"]
    }

    skill_bind_variants = tag("Floor 6", "Skill bind")["variants"]
    assert any(
        variant["details"] == ["for 2 turns"]
        and variant["sources"] == ["Altema"]
        for variant in skill_bind_variants
    )
    assert any(
        variant["details"] == ["for 5 turns"]
        and set(variant["sources"]) == {"AppMedia", "Game8", "GameWith"}
        for variant in skill_bind_variants
    )
    floor5_absorb = tag("Floor 5", "Damage absorb")["variants"]
    assert floor5_absorb == [
        {
            "when": "Preemptive",
            "details": ["for 4 turns", "5B or more"],
            "sources": ["Altema", "AppMedia", "Game8", "GameWith"],
        }
    ]

    buff_void_variants = tag("Floor 3", "Void buffs")["variants"]
    assert {variant["when"] for variant in buff_void_variants} == {
        "If 11 or fewer combos",
        "If 12 or fewer combos",
        "Puzzle test failed",
    }

    enrage_variants = tag("Floor 15", "Enrage")["variants"]
    assert any(
        variant["when"] == "When all parts break"
        for variant in enrage_variants
    )
    floor9_enrage = tag("Floor 9", "Enrage")["variants"]
    assert len(floor9_enrage) == 1
    assert floor9_enrage[0]["when"] == "Action 3"
    assert set(floor9_enrage[0]["sources"]) == {"AppMedia", "GameWith"}

    puzzle_success = tag("Floor 3", "Super blind")["variants"]
    assert len(puzzle_success) == 1
    passed = next(
        variant
        for variant in puzzle_success
        if variant["when"] == "Puzzle test passed (12+ combos)"
    )
    assert set(passed["sources"]) == {"Altema", "AppMedia", "Game8", "GameWith"}

    floor14_assist = tag("Floor 14", "Assist bind")["variants"]
    assert any(
        variant["when"] == "Action 3"
        and set(variant["sources"]) == {"AppMedia", "GameWith"}
        for variant in floor14_assist
    )
    assert any(
        variant["when"] == "Action 6"
        and set(variant["sources"]) == {"AppMedia", "GameWith"}
        for variant in floor14_assist
    )
    floor14_damage_absorb = tag("Floor 14", "Damage absorb")["variants"]
    assert floor14_damage_absorb == [
        {
            "when": "Action 2",
            "details": ["for 1 turn", "5B or more"],
            "sources": ["AppMedia", "GameWith"],
        }
    ]

    assert data["summary"]["Damage absorb"]
    assert data["summary"]["Attribute absorb"]
    assert data["summary"]["Roulette"]
    assert "DEF +5B" in tag("Floor 1", "Enemy DEF up")["details"][0]
    assert "50%" in tag("Floor 4", "Resolve")["details"]
    assert "40%" in tag("Floor 5", "Super resolve")["details"]
    assert "All colors" in tag("Floor 2", "Roulette")["details"][0]
    assert any("Water, Dark, Heart" in detail for detail in tag("Floor 12", "Roulette")["details"])
    floor2_roulette = tag("Floor 2", "Roulette")["variants"]
    assert len(floor2_roulette) == 1
    assert floor2_roulette[0]["details"] == [
        "for 1 turn",
        "All colors",
        "4 orbs",
    ]
    assert set(floor2_roulette[0]["sources"]) == {
        "Altema",
        "AppMedia",
        "Game8",
        "GameWith",
    }
    floor9_roulette = tag("Floor 9", "Roulette")["variants"]
    assert len(floor9_roulette) == 1
    assert floor9_roulette[0]["details"] == [
        "for 4 turns",
        "All colors",
        "Bottom row",
        "6 orbs",
    ]
    assert set(floor9_roulette[0]["sources"]) == {
        "Altema",
        "AppMedia",
        "Game8",
        "GameWith",
    }
    floor12_roulette = tag("Floor 12", "Roulette")["variants"]
    assert len(floor12_roulette) == 1
    assert {
        tuple(variant["details"]): set(variant["sources"])
        for variant in floor12_roulette
    } == {
        ("for 4 turns", "Water, Dark, Heart", "2 orbs"): {
            "AppMedia",
            "Altema",
            "Game8",
            "GameWith",
        },
    }
    floor14_roulette = tag("Floor 14", "Roulette")["variants"]
    assert len(floor14_roulette) == 1
    assert floor14_roulette[0]["details"][-1] == "2 orbs"
    assert set(floor14_roulette[0]["sources"]) == {"AppMedia", "GameWith"}
    floor15_roulette = tag("Floor 15", "Roulette")["variants"]
    assert len(floor15_roulette) == 1
    assert floor15_roulette[0]["details"] == [
        "for 4 turns",
        "All colors",
        "2 orbs",
    ]
    assert set(floor15_roulette[0]["sources"]) == {
        "Altema",
        "AppMedia",
        "GameWith",
    }
    assert "Damage cap set" in data["summary"]
    floor9_damage_void = tag("Floor 9", "Damage void")["variants"]
    assert {variant["when"] for variant in floor9_damage_void} == {
        "Action 2",
        "Below 50% HP",
    }
    floor1_enrage = tag("Floor 1", "Enrage")["variants"]
    assert {variant["when"] for variant in floor1_enrage} == {
        "When 1 remains",
        "When 2 or fewer remain",
    }

    assert data["normal_hit_baseline"] == 10_657_500
    floor9_enraged_hit = next(
        action
        for enemy in floors["Floor 9"]["enemies"]
        for action in enemy["actions"]
        if action["hit"] == 10_710_000
    )
    floor15_enraged_hit = next(
        action
        for enemy in floors["Floor 15"]["enemies"]
        for action in enemy["actions"]
        if action["hit"] == 55_200_000
    )
    floor15_normal_hit = next(
        action
        for enemy in floors["Floor 15"]["enemies"]
        for action in enemy["actions"]
        if action["hit"] == 20_400_000
    )
    floor5_normal_hit = next(
        action
        for enemy in floors["Floor 5"]["enemies"]
        for action in enemy["actions"]
        if action["hit"] == 7_400_000
    )
    floor6_normal_hit = next(
        action
        for enemy in floors["Floor 6"]["enemies"]
        for action in enemy["actions"]
        if action["when"] == "Normal action" and action["hit"] == 4_200_000
    )
    invade_break_hit = next(
        action
        for enemy in floors["Invade (Floor 6 or 8)"]["enemies"]
        for action in enemy["actions"]
        if action["when"] == "When a part breaks" and action["hit"] is not None
    )
    assert not floor9_enraged_hit["enraged"]
    assert floor9_enraged_hit["normal_hit"] == 10_710_000
    assert floor9_enraged_hit["enraged_hit"] == 53_550_000
    assert floor15_enraged_hit["enraged"]
    assert floor15_enraged_hit["enraged_hit"] is None
    assert not floor15_normal_hit["enraged"]
    assert floor15_normal_hit["enraged_hit"] == 26_520_000
    assert not floor5_normal_hit["enraged"]
    assert floor6_normal_hit["enraged_hit"] == 42_000_000
    assert not invade_break_hit["enraged"]
    assert invade_break_hit["normal_hit"] == 7_984_050
    assert invade_break_hit["enraged_hit"] == 10_379_265
    progression = data["damage_progression"]
    assert progression["range_change_multiple"] == 1.5
    assert 7 in progression["missing_floors"]
    assert 11 in progression["missing_floors"]
    assert 1 not in progression["missing_floors"]
    assert any(item["label"] == "Floor 1" for item in progression["excluded_floors"])
    assert any(
        item["label"] == "Floors 2–6"
        and item["median_hit"] == 7_200_000
        and item["min_hit"] == 6_120_000
        and item["max_hit"] == 8_400_000
        for item in progression["ranges"]
    )
    all_actions = [
        action
        for floor in floors.values()
        for enemy in floor["enemies"]
        for action in enemy["actions"]
    ]
    assert "Damage cap set to 2B" in next(
        action["text"] for action in all_actions
        if action["text"].startswith("Damage cap set")
    )
    assert any(
        "Resolve at 50%" in enemy["traits"]
        for floor in floors.values()
        for enemy in floor["enemies"]
    )
    assert any("Super resolve at 40%" in enemy["traits"] for enemy in floors["Floor 5"]["enemies"])
    assert any("ATK reduced by 75%" in action["text"] for action in all_actions)
    assert any(
        "ATK reduced by 80%" in " ".join(variant["details"])
        for variant in tag("Floor 12", "Your ATK down")["variants"]
    )
    assert any(
        "Move-time change" in action["text"] and "×2" in action["text"]
        for action in all_actions
    )
    assert any(
        action["text"] == "Normal attack" and action["hit"] is not None
        for action in all_actions
    )
    floor3_text = [
        action["text"]
        for enemy in floors["Floor 3"]["enemies"]
        for action in enemy["actions"]
    ]
    assert "Skill haste +2 turns" in floor3_text
    floor3_actions = [
        action
        for enemy in floors["Floor 3"]["enemies"]
        for action in enemy["actions"]
    ]
    assert any(
        action["when"] == "Normal action 1" and action["hit"] == 7_000_000
        for action in floor3_actions
    )
    assert any(
        action["when"] == "Normal action 2" and action["hit"] == 7_140_000
        for action in floor3_actions
    )
    assert any(
        action["text"] == "Generate 1 shield"
        for floor in floors.values()
        for enemy in floor["enemies"]
        for action in enemy["actions"]
    )
    severities = {
        floor: {
            action["severity"]
            for enemy in floors[floor]["enemies"]
            for action in enemy["actions"]
            if action["severity"] is not None
        }
        for floor in floors
    }
    for floor in ("Floor 5", "Floor 11", "Floor 15"):
        assert "large" in severities[floor]
        assert "execute" not in severities[floor]
    assert "execute" in severities["Floor 3"]
    large_multiples = {
        floor: max(
            action["severity_multiple"]
            for enemy in floors[floor]["enemies"]
            for action in enemy["actions"]
            if action["severity"] == "large"
        )
        for floor in ("Floor 5", "Floor 11", "Floor 15")
    }
    assert large_multiples == {
        "Floor 5": 4.0,
        "Floor 11": 4.5,
        "Floor 15": 5.0,
    }


def test_published_actions_keep_timing_order_and_source(gamewith_record):
    manifest_path = Path(__file__).parents[1] / "dungeons.json"
    entry = json.loads(manifest_path.read_text(encoding="utf-8"))[0]
    record = annotate_record(gamewith_record)
    record["floors"][0]["enemies"][0]["actions"].append(
        annotate_action(
            {
                "source": "gamewith",
                "timing_jp": "通常行動",
                "text_jp": "未登録の行動",
            }
        )
    )
    merged, _ = merge_dungeon(entry, {"gamewith": record}, {})
    published = _publish_dungeon(entry, merged, {"gamewith": record}, "test")
    debug = _publish_dungeon(entry, merged, {"gamewith": record}, "test", debug=True)
    floor14 = next(floor for floor in published["floors"] if floor["number"] == 14)
    actions = [action for enemy in floor14["enemies"] for action in enemy["actions"]]
    ordered = [action for action in actions if action["timing_kind"] == "sequence"]

    assert ordered
    assert all(action["source"] == "GameWith" for action in ordered)
    assert {action["order"] for action in ordered if action["order"] is not None}
    assert all("text_jp" not in action and "timing_jp" not in action for action in actions)
    debug_actions = [
        action
        for floor in debug["floors"]
        for enemy in floor["enemies"]
        for action in enemy["actions"]
    ]
    assert any(action.get("untranslated_text_jp") for action in debug_actions)
    expected_untranslated = next(
        action["text_jp"]
        for floor in record["floors"]
        for enemy in floor["enemies"]
        for action in enemy["actions"]
        if not action["text"] and action.get("text_jp")
    )
    assert expected_untranslated in {
        action["untranslated_text_jp"]
        for action in debug_actions
        if action.get("untranslated_text_jp")
    }
    assert all(
        "untranslated_text_jp" not in action
        for floor in published["floors"]
        for enemy in floor["enemies"]
        for action in enemy["actions"]
    )


def test_unlisted_resolve_threshold_defaults_to_half():
    assert english_trait("根性") == "Resolve at 50%"
    assert english_trait("超根性") == "Super resolve at 50%"
    assert english_trait("超根性:40%") == "Super resolve at 40%"


def test_floor3_puzzle_failure_is_conditional_175m_hit(
    gamewith_record, appmedia_record, altema_record
):
    gamewith_floor = _floor(annotate_record(gamewith_record), 3)
    gamewith_actions = _actions({"floors": [gamewith_floor]})
    failure_hit = next(action for action in gamewith_actions if action["hit"] == 175_000_000)
    assert failure_hit["when"] == "Puzzle test failed"
    assert any(
        action["when"] == "Puzzle test failed" and "Void buffs" in action["tags"]
        for action in gamewith_actions
    )
    assert any(
        action["when"] == "Preemptive" and "Invulnerable" in action["tags"]
        for action in gamewith_actions
    )
    assert all(
        action["when"] == "Preemptive"
        for action in gamewith_actions
        if {"Awoken bind", "Bind"} & set(action["tags"])
    )

    appmedia_actions = _actions({"floors": [_floor(annotate_record(appmedia_record), 3)]})
    assert any(
        action["when"] == "If 12 or fewer combos"
        and action["hit"] == 175_000_000
        for action in appmedia_actions
    )
    altema_actions = _actions({"floors": [_floor(annotate_record(altema_record), 3)]})
    assert any(
        action["when"] == "If 11 or fewer combos"
        and action["hit"] == 175_000_000
        for action in altema_actions
    )


def test_report_lists_japanese_for_items_without_english_annotation(gamewith_record):
    manifest_path = Path(__file__).parents[1] / "dungeons.json"
    entry = json.loads(manifest_path.read_text(encoding="utf-8"))[0]
    record = copy.deepcopy(gamewith_record)
    invade = next(floor for floor in record["floors"] if floor["number"] is None)
    boss = next(enemy for enemy in invade["enemies"] if enemy["card"] == 10981)
    boss["parts"][0]["name_jp"] = "未訳部位"
    boss["traits_jp"].append("未訳特性")
    merged, diagnostics = merge_dungeon(entry, {"gamewith": record}, {})
    report = _render_report([(merged, diagnostics)])

    assert "Actions without English annotation" in report
    assert "gamewith · Invade · Card 10981" in report
    assert "7,984,050ダメージ" not in report
    assert "Enemies without English names" in report
    assert "レモック(変身)" in report
    assert "Part names without an English mapping" in report
    assert "未訳部位" in report
    assert "Enemy traits without an English mapping" in report
    assert "未訳特性" in report
    assert "超高度(回復力が20分の1)" in report
