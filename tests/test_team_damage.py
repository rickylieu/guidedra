import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "site" / "team-damage.mjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")
B = 1_000_000_000


def run(body):
    script = (
        "import * as t from " + json.dumps(MODULE.as_uri()) + ";\n"
        "const out = (() => {" + body + "})();\n"
        "console.log(JSON.stringify(out));\n"
    )
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_attribute_triangle_and_light_dark():
    assert run("""return [
        t.attributeMultiplier('Fire', 'Wood'),
        t.attributeMultiplier('Fire', 'Water'),
        t.attributeMultiplier('Light', 'Dark'),
        t.attributeMultiplier('Dark', 'Light'),
        t.attributeMultiplier('Light', 'Fire'),
        t.attributeMultiplier('Fire', undefined),
    ]""") == [2, 0.5, 2, 2, 1, 1]


def test_parse_billions():
    assert run("return [t.parseBillions('35'), t.parseBillions('35B'), t.parseBillions('3.5'), t.parseBillions('')]") == [
        35 * B, 35 * B, None, None,
    ]


def test_effective_damage_mixed_team():
    assert run("return t.effectiveDamage({Fire: 10e9, Water: 10e9}, 'Wood')") == 25 * B


def test_absorbed_colour_is_zero():
    assert run("return t.effectiveDamage({Fire: 10e9, Water: 10e9}, 'Wood', ['Fire'])") == 5 * B


def test_halved_attribute():
    assert run("return t.effectiveDamage({Light: 10e9}, 'Dark', [], ['Light'])") == 10 * B


def test_halved_attributes_from_traits():
    assert run("return t.halvedAttributes(['Takes half damage from Light', 'Takes half damage from God types'])") == ["Light"]


def test_turns_across_attribute_switch():
    result = run("return t.floorTurns([{hp: 100e9, attributes: ['Fire', 'Wood']}], {Water: 10e9})")
    assert result == {"turns": 13, "capped": False}


def test_absorb_duration_delays_clear():
    result = run("return t.floorTurns([{hp: 20e9, attributes: ['Fire']}], {Light: 10e9}, {colors: ['Light'], turns: 2})")
    assert result == {"turns": 4, "capped": False}


def test_no_damage_is_capped():
    result = run("return t.floorTurns([{hp: 20e9, attributes: ['Fire']}], {Fire: 10e9}, {colors: ['Fire'], turns: 99}, 99)")
    assert result == {"turns": 99, "capped": True}


def test_red_flag_rules():
    assert run("""const fire = new Set(['Fire']);
    const dark = new Set(['Dark']);
    const water = new Set(['Water']);
    return [
        t.affectsTeam('Attribute absorb', ['for 4 turns', 'Fire, Light'], fire),
        t.affectsTeam('Attribute absorb', ['for 4 turns', 'Fire, Light'], water),
        t.affectsTeam('Unmatchable', ['for 1 turn, Heart'], fire),
        t.affectsTeam('Roulette', ['for 4 turns', 'Dark, Heart', '2 orbs'], fire),
        t.affectsTeam('Roulette', ['for 4 turns', 'Dark, Heart', '2 orbs'], dark),
        t.affectsTeam('Roulette', ['for 4 turns', 'All colors', '2 orbs'], fire),
        t.affectsTeam('Roulette', ['for 4 turns - Dark, Heart - 2 orbs'], fire),
    ]""") == [True, False, False, True, False, False, True]


def test_team_total_label():
    assert run(
        "return [t.teamTotalLabel({Fire: 20e9, Water: 15e9}), t.teamTotalLabel({}), t.teamTotalLabel(null)]"
    ) == ["Total: 35B", None, None]
