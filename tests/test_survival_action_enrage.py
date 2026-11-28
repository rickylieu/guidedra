import json
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).parents[1] / "site"


def node(call):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    url = (SITE / "team-shield.mjs").as_uri()
    script = f'import * as m from "{url}"; console.log(JSON.stringify({call}));'
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def slow(enrage):
    return node(f"m.isSlowEnrage({json.dumps(enrage)})")


def test_numbered_moves_count_as_turns():
    assert slow({"tags": ["Enrage"], "timing_kind": "nth_action", "when": "Action 3"}) is True
    assert slow({"tags": ["Enrage"], "timing_kind": "normal", "when": "Normal action 3"}) is True
    assert slow({"tags": ["Enrage"], "timing_kind": "sequence", "when": "Repeats in order", "order": 3}) is True
    assert slow({"tags": ["Enrage"], "timing_kind": "nth_action", "when": "Action 2"}) is False
    assert slow({"tags": ["Enrage"], "timing_kind": "first_action", "when": "First action"}) is False


def test_uranus_hits_checked_at_normal_damage():
    for path in SITE.joinpath("data").glob("*.json"):
        if path.name.endswith("-debug.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            continue
        for floor in data.get("floors", []):
            for enemy in floor.get("enemies", []):
                if enemy.get("card") != 7278:
                    continue
                actions = enemy.get("actions", [])
                for action in actions:
                    got = node(f"m.survivalDamage({json.dumps(action)}, {json.dumps(actions)})")
                    where = f"{path.name} {floor['label']}: {action.get('when')}"
                    if "Enrage" in action.get("tags", []):
                        assert got is None, where
                    elif isinstance(action.get("hit"), int) and not action.get("already_enraged"):
                        normal = action.get("normal_hit")
                        expected = normal if isinstance(normal, int) else action["hit"]
                        assert got == expected, where
                return
    pytest.skip("Reincarnated Uranus (7278) not in built data")
