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


def test_survival_alert():
    assert node("m.survivalAlert(90, 100, null, false)") is None
    assert node("m.survivalAlert(100, 100, null, false)") == "Can't survive"
    assert node("m.survivalAlert(150, 100, 200, false)") == "Larger shield needed"
    assert node("m.survivalAlert(250, 100, 200, false)") == "Can't survive"
    assert node("m.survivalAlert(60, 100, null, true)") == "Can't survive"
    assert node("m.survivalAlert(null, 100, null, false)") is None


def test_looping_shield_in_working():
    sources = [
        {"role": "Leader", "card": 10981, "name": "Lemocks", "shields": [{"pct": 75}]},
        {"role": "Looping shield", "card": None, "shields": [{"pct": 50}]},
    ]
    lines = node(f"m.explainEffectiveHp(50000, {json.dumps(sources)})")
    assert lines[:2] == ["Leader Lemocks (10981): 75% shield", "Looping shield: 50% shield"]
    assert lines[-1] == "Effective HP = 50,000 ÷ (1 − 0.875) = 50,000 ÷ 0.125 = 400,000"


def test_app_wiring():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert "const SHOW_MEDIAN = false;" in app
    assert "function legacyAlertForAction(" in app
    assert "teamField(loopingLabel, loopingInput)" in app
    assert "teamField(largerLabel, largerInput)" in app
    assert "renderSurvivalWarning(data, teamHp)" in app
    assert "Hits you can't survive" in app
    assert ".survival-warning {" in (SITE / "style.css").read_text(encoding="utf-8")
