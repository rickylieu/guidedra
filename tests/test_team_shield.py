import json
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).parents[1] / "site"


def run(team_hp, shields):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    url = (SITE / "team-shield.mjs").as_uri()
    script = (
        f'import {{ effectiveHpRange }} from "{url}";'
        f"console.log(JSON.stringify(effectiveHpRange({json.dumps(team_hp)}, {json.dumps(shields)})));"
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_no_shield():
    assert run(1_000_000, []) == {"low": 1_000_000, "high": 1_000_000, "lowPct": 0, "highPct": 0}


def test_flat_shield():
    assert run(1_000_000, [{"pct": 75}])["low"] == 4_000_000


def test_leader_and_helper_multiply():
    r = run(1_000_000, [{"pct": 50}, {"pct": 50}])
    assert (r["low"], r["lowPct"]) == (4_000_000, 75)


def test_hp_threshold_gives_range():
    r = run(1_000_000, [{"pct": 50, "hp_at_least": 80}])
    assert (r["low"], r["high"]) == (1_000_000, 2_000_000)
    r = run(1_000_000, [{"pct": 50}, {"pct": 50, "hp_at_most": 50}])
    assert (r["low"], r["high"]) == (2_000_000, 4_000_000)


def test_no_team_hp():
    assert run(None, [{"pct": 50}]) is None


def test_app_uses_effective_hp():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert "function rawTeamHp()" in app
    assert 'import("./team-shield.mjs")' in app
    assert "effectiveHpRange(hp, list.flatMap" in app
    assert "buffedHp(raw, loopingBuff)" in app
    assert "explainEffectiveHp(hp, list)" in app
    assert "data/card_shields.json" in app


def explain(team_hp, sources):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    url = (SITE / "team-shield.mjs").as_uri()
    script = (
        f'import {{ explainEffectiveHp }} from "{url}";'
        f"console.log(JSON.stringify(explainEffectiveHp({json.dumps(team_hp)}, {json.dumps(sources)})));"
    )
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_work_shown_for_leader_and_helper():
    lines = explain(50_000, [
        {"role": "Leader", "card": 10981, "shields": [{"pct": 75}]},
        {"role": "Helper", "card": 1234, "shields": [{"pct": 50}]},
    ])
    assert lines == [
        "Leader card 10981: 75% shield",
        "Helper card 1234: 50% shield",
        "Effective Shield = 1 − (1 − 0.75) × (1 − 0.5) = 1 − 0.125 = 0.875 (87.5%)",
        "Effective HP = 50,000 ÷ (1 − 0.875) = 50,000 ÷ 0.125 = 400,000",
    ]


def test_work_single_shield_rounds_to_whole():
    lines = explain(33_333, [{"role": "Leader", "card": 10981, "shields": [{"pct": 75}]}])
    assert lines[-1] == "Effective HP = 33,333 ÷ (1 − 0.75) = 33,333 ÷ 0.25 = 133,332"
    lines = explain(10_000, [{"role": "Leader", "card": 1, "shields": [{"pct": 35}]}])
    assert lines[-1] == "Effective HP = 10,000 ÷ (1 − 0.35) = 10,000 ÷ 0.65 = 15,384"


def test_work_card_without_shield():
    assert explain(50_000, [{"role": "Helper", "card": 1234, "shields": []}]) == ["Helper card 1234: no leader shield"]


def test_work_hp_threshold_splits_by_hp():
    lines = explain(100_000, [{"role": "Leader", "card": 5, "shields": [{"pct": 50, "hp_at_least": 80}]}])
    assert lines == [
        "Leader card 5: 50% shield at 80% HP or above",
        "At 1–79% HP: no shield",
        "Effective HP = 100,000",
        "At 80–100% HP: Effective Shield = 50%",
        "Effective HP = 100,000 ÷ (1 − 0.5) = 100,000 ÷ 0.5 = 200,000",
        "Shield needed uses the lowest: 100,000",
    ]


def test_work_shows_card_name():
    lines = explain(50_000, [
        {"role": "Leader", "card": 10981, "name": "Lemocks", "shields": [{"pct": 75}]},
        {"role": "Helper", "card": 1234, "name": "Some Helper", "shields": []},
    ])
    assert lines[:2] == ["Leader Lemocks (10981): 75% shield", "Helper Some Helper (1234): no leader shield"]


def test_card_names_published():
    path = SITE / "data" / "card_names.json"
    if not path.exists():
        pytest.skip("card_names.json not copied")
    assert "10981" in json.loads(path.read_text(encoding="utf-8"))
    assert 'fetch("data/card_names.json")' in (SITE / "app.js").read_text(encoding="utf-8")


def test_effective_hp_rounds_down():
    assert run(10_000, [{"pct": 35}])["low"] == 15_384
    assert run(30_000, [{"pct": 70}])["low"] == 100_000
    lines = explain(30_000, [{"role": "Leader", "card": 1, "shields": [{"pct": 70}]}])
    assert lines[-1] == "Effective HP = 30,000 ÷ (1 − 0.7) = 30,000 ÷ 0.3 = 100,000"


def test_effective_shield_label():
    lines = explain(50_000, [{"role": "Leader", "card": 10981, "name": "Lemocks", "shields": [{"pct": 75}]}])
    assert lines[1] == "Effective Shield = 75%"
    assert not any(line.startswith("Shield = ") for line in lines)

