"""Regression tests for the Nov 25-26 2026 additions."""
import json
from pathlib import Path

import pytest

from build import _enraged_hit_values
from glossary import annotate_action, english_trait, extract_tags, parse_timing
from merge import _fold_unspecified_amounts
from rules import floor_label

DATA = Path(__file__).parents[1] / "site" / "data"


def act(text, timing=""):
    return annotate_action({"timing_jp": timing, "text_jp": text, "order": None})


def load(slug):
    path = DATA / f"{slug}.json"
    if not path.exists():
        pytest.skip(f"{path.name} not built")
    return json.loads(path.read_text(encoding="utf-8"))


# rules.py: invade floor label
def test_invade_label_three_floors():
    assert floor_label({"number": None, "invade_floors": [2, 3, 4]}) == "Invade (Floor 2, 3, or 4)"


def test_invade_label_two_floors_unchanged():
    assert floor_label({"number": None, "invade_floors": [6, 8]}) == "Invade (Floor 6 or 8)"


def test_numbered_and_bare_labels_unchanged():
    assert floor_label({"number": 3, "invade_floors": []}) == "Floor 3"
    assert floor_label({"number": None, "invade_floors": []}) == "Invade"


# glossary.py: wording
def test_multi_hit_attack():
    action = act("6,370,000ダメージの連続攻撃")
    assert action["text"] == "Multi-hit attack"
    assert action["hit"] == 6_370_000


def test_plain_hit_still_normal_attack():
    assert act("8,585,000ダメージ")["text"] == "Normal attack"


def test_thorn_count_wording():
    assert act("ドロップ5個トゲ")["text"].startswith("Create 5 thorn orbs")


def test_one_shot_required_tag():
    assert "One-shot required" in extract_tags("ワンパン必須")


def test_god_type_half_damage_trait():
    assert english_trait("神タイプ半減") == "Takes half damage from God types"


def test_details_separator_is_dash():
    assert act("操作時間半減(2ターン)", "通常行動")["text"] == "Move-time change (for 2 turns - reduced by 50%)"


def test_reduce_atk_with_number():
    action = act("攻撃力0.2倍(2ターン)")
    assert "Reduce ATK" in action["tags"]
    assert "by 80%" in action["text"]


# glossary.py: poison, skyfall, destroy
def test_poison_skyfall_is_skyfall_increase_not_poison():
    action = act("[猛毒]目覚め(4ターン)")
    assert "Skyfall increase" in action["tags"]
    assert "Poison" not in action["tags"]
    assert "Mortal poison" in action["text"]


def test_poison_roulette_has_no_poison_tag():
    action = act("[闇][回復][毒][猛毒]のルーレットを2個生成(4ターン)")
    assert "Roulette" in action["tags"]
    assert "Poison" not in action["tags"]
    assert "Mortal poison" in action["text"]


def test_destroy_two_colours():
    assert act("[水][闇]を破壊")["text"].startswith("Destroy water and dark orbs")


def test_destroy_three_colours():
    assert act("[火][水][闇]を破壊")["text"].startswith("Destroy fire, water, and dark orbs")


def test_destroy_bombs_has_no_bombs_tag():
    assert "Bombs" not in act("[爆弾]を破壊")["tags"]


# glossary.py: timings
def test_numbered_normal_action_from_header():
    label = parse_timing("通常行動②")["label"]
    assert label.startswith("Normal action") and "2" in label


def test_countdown_timing_kind():
    assert parse_timing("呪いのカウントダウン3")["kind"] == "countdown"


def test_already_enraged_hit_is_flagged():
    action = act("7,850,700ダメージ（1.3倍時）")
    assert action["hit"] == 7_850_700
    assert action.get("already_enraged") is True


# build.py: already-enraged hits are not multiplied again
def test_already_enraged_not_multiplied():
    assert _enraged_hit_values({"hit": 7_850_700, "already_enraged": True}, 1.3) == (7_850_700, 7_850_700)


# merge.py: a stated amount beats an unspecified one
WHEN = ("label", "On super resolve")


def test_unspecified_amount_folds_into_stated():
    vague = (WHEN, ("for 2 turns", "ATK greatly reduced (percentage unspecified)"))
    stated = (WHEN, ("for 2 turns", "ATK reduced by 80%"))
    folded = _fold_unspecified_amounts({vague: {"AppMedia", "Game8", "GameWith"}, stated: {"Altema"}})
    assert folded == {stated: {"Altema", "AppMedia", "Game8", "GameWith"}}


def test_two_stated_amounts_do_not_fold():
    vague = (WHEN, ("for 2 turns", "ATK greatly reduced (percentage unspecified)"))
    a = (WHEN, ("for 2 turns", "ATK reduced by 80%"))
    b = (WHEN, ("for 2 turns", "ATK reduced by 75%"))
    variants = {vague: {"AppMedia"}, a: {"Altema"}, b: {"GameWith"}}
    assert _fold_unspecified_amounts(variants) == variants


# published JSON
def test_quest_ex_rush_published_facts():
    data = load("quest-ex-rush-2026-11")
    floors = {floor["label"]: floor for floor in data["floors"]}
    assert "Invade (Floor 2, 3, or 4)" in floors
    assert "One-shot required" in {tag["name"] for tag in floors["Floor 4"]["tags"]}


def test_december_already_enraged_hit_published():
    data = load("december-2026-ex-rush")
    hits = [
        action
        for floor in data["floors"]
        for enemy in floor["enemies"]
        for action in enemy["actions"]
        if action.get("normal_hit") == 7_850_700
    ]
    assert hits and all(action["enraged_hit"] == 7_850_700 for action in hits)


def test_no_countdown_timings_left_unconverted():
    for path in DATA.glob("*.json"):
        if path.name in {"index.json", "card_elements.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for floor in data.get("floors", []):
            for enemy in floor["enemies"]:
                for action in enemy["actions"]:
                    assert not action["when"].startswith("Countdown"), (path.name, floor["label"])
