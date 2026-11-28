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


def damage(action, enemy_actions):
    return node(f"m.survivalDamage({json.dumps(action)}, {json.dumps(enemy_actions)})")


HIT = {"tags": [], "hit": 100, "normal_hit": 100, "enraged_hit": 500}


def enrage(kind, when):
    return {"tags": ["Enrage"], "timing_kind": kind, "when": when, "hit": None}


def test_slow_enrages_left_out():
    turn3 = enrage("turn", "Turn 3")
    assert damage(HIT, [HIT, turn3]) == 100
    assert damage(turn3, [HIT, turn3]) is None
    assert damage({**HIT, "already_enraged": True}, [HIT, turn3]) is None
    left = enrage("remaining_eq", "When 1 remains")
    assert damage(HIT, [HIT, left]) == 100


def test_fair_enrages_still_count():
    assert damage(HIT, [HIT, enrage("turn", "Turn 2")]) == 500
    assert damage(HIT, [HIT, enrage("hp_below", "Below 50% HP")]) == 500
    both = [HIT, enrage("turn", "Turn 3"), enrage("hp_below", "Below 50% HP")]
    assert damage(HIT, both) == 500
    assert damage(HIT, [HIT]) == 500


def test_app_wiring():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert "damageCheck = shieldMaths.survivalDamage;" in app
    assert "survivalCheck(actionDamage(action, floor)," in app
    assert "const damage = actionDamage(action, floor);" in app
