import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).parents[1] / "site"
APP = (SITE / "app.js").read_text(encoding="utf-8")


def run(call):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    funcs = "\n".join(
        re.search(rf"^function {name}\(.*?^}}\n", APP, re.S | re.M).group(0)
        for name in ("floorEnrageReasons", "enemyOf", "hitWord")
    )
    out = subprocess.run(["node", "-e", funcs + f"\nconsole.log(JSON.stringify({call}));"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


ENEMY = """{actions: [
  {when: "Below 50% HP", text: "Enemy ATK up (x1.5)", tags: ["Enemy ATK up"]},
  {when: "Turn 1", text: "Normal attack", tags: [], hit: 10, enraged_hit: 15},
  {when: "Turn 2", text: "Normal attack", tags: [{name: "Big hit / lethal"}], hit: 20, already_enraged: true, severity: "large"}
]}"""

TWO_ENRAGES = """{actions: [
  {when: "Preemptive", text: "Enemy ATK up (for 1 turn - ×3)", tags: [{name: "Enemy ATK up"}]},
  {when: "When a part breaks", text: "Enemy ATK up (×1.3)", tags: [{name: "Enemy ATK up"}]},
  {when: "Action 1", text: "Normal attack", tags: [], hit: 20000000, enraged_hit: 26000000},
  {when: "Action 2", text: "Normal attack", tags: [], hit: 20000000, already_enraged: true}
]}"""

FLOOR_15 = """{
  tags: [{name: "Enrage", variants: [{when: "When all parts break", details: ["×1.3", "for 999 turns"]}]}],
  enemies: [{actions: [
    {when: "Preemptive", text: "Enemy ATK up, Preemptive (for 1 turn - ×3)", tags: ["Enemy ATK up", "Preemptive"]},
    {when: "One at random", text: "Damage void", tags: ["Damage void"], hit: 20400000, enraged_hit: 26520000}
  ]}]
}"""


def test_hit_word():
    assert run(f"hitWord({ENEMY}.actions[1], {ENEMY}, 10)") == "normal hit"
    assert run(f"hitWord({ENEMY}.actions[1], {ENEMY}, 15)") == "enraged normal hit (Below 50% HP: Enemy ATK up (x1.5))"
    assert run(f"hitWord({ENEMY}.actions[2], {ENEMY}, 20)") == "enraged large hit (Below 50% HP: Enemy ATK up (x1.5))"
    assert run('hitWord({hit: 5, enraged_hit: 9}, null, 9)') == "enraged normal hit"
    assert run(f"(() => {{ const e = {ENEMY}; return enemyOf({{enemies: [e]}}, e.actions[1]) === e; }})()") is True


def test_large_or_normal():
    assert run('hitWord({hit: 50, severity: "large"}, null, 50)') == "large hit"
    assert run('hitWord({hit: 50, severity: null}, null, 50)') == "normal hit"


def test_reason_matches_multiplier():
    got = run(f"(() => {{ const e = {TWO_ENRAGES}; return hitWord(e.actions[2], e, 26000000); }})()")
    assert got == "enraged normal hit (When a part breaks: Enemy ATK up (×1.3))"
    got = run(f"(() => {{ const e = {TWO_ENRAGES}; return hitWord(e.actions[3], e, 20000000); }})()")
    assert got == "enraged normal hit"


def test_reason_from_floor_tags():
    got = run(f"(() => {{ const f = {FLOOR_15}; const e = f.enemies[0]; return hitWord(e.actions[1], e, 26520000, f); }})()")
    assert got == "enraged normal hit (When all parts break: Enrage (×1.3 - for 999 turns))"


def test_wiring():
    assert "hitWord(action, enemyOf(floor, action), damage, floor)" in APP
    assert "largerWhat.toLowerCase()" not in APP
    assert 'element("div", "team-break", ""),\n  teamField(loopingHpLabel, loopingHpInput),' in APP
    assert ".team-break {" in (SITE / "style.css").read_text(encoding="utf-8")
