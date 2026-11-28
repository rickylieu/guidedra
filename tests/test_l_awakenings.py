import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP = (Path(__file__).parents[1] / "site" / "app.js").read_text(encoding="utf-8")


def run(value, checked):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    func = re.search(r"^function lAwakeningSource\(.*?^}\n", APP, re.S | re.M).group(0)
    js = (
        "const shieldSource = (role, input) => ({ role, pct: input.value });\n"
        f"const lAwakeningsInput = {{ value: {json.dumps(value)} }};\n"
        f"const lAwakeningsCheck = {{ checked: {json.dumps(checked)} }};\n"
        + func
        + "\nconsole.log(JSON.stringify(lAwakeningSource() ?? null));"
    )
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_six_is_thirty_percent():
    assert run("6", True) == {"role": "L awakenings (6 × 5%)", "pct": "30"}


def test_unchecked_ignores_count():
    assert run("6", False) is None


def test_blank_or_zero():
    assert run("", True) is None
    assert run("0", True) is None


def test_capped_at_19():
    assert run("25", True) == {"role": "L awakenings (19 × 5%)", "pct": "95"}


def test_wiring():
    assert "Include L awakenings in damage calculations" in APP
    assert "teamField(lAwakeningsLabel, lAwakeningsInput)" in APP
    assert "const sources = [...cards, looping, lAwake].filter(Boolean);" in APP
    assert "[...cards, larger || looping, lAwake].filter(Boolean)" in APP
