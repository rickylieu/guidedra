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


def test_puzzle_fail():
    fail = {"timing_kind": "lesson_fail"}
    le = {"timing_kind": "combo_le"}
    ge = {"timing_kind": "combo_ge"}
    assert node(f"m.isPuzzleFail({json.dumps(fail)}, [])") is True
    assert node(f"m.isPuzzleFail({json.dumps(le)}, {json.dumps([ge, le])})") is True
    assert node(f"m.isPuzzleFail({json.dumps(le)}, {json.dumps([le])})") is False
    assert node(f"m.isPuzzleFail({json.dumps(ge)}, {json.dumps([ge, le])})") is False


def test_app_skips_executes_and_puzzle_fails():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert 'if (action.severity === "execute") return "Execute";' in app
    assert "puzzleFailCheck = shieldMaths.isPuzzleFail;" in app
    assert "if (puzzleFailCheck && puzzleFailCheck(action, enemy?.actions || [])) return null;" in app
