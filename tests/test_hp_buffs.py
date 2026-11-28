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
        for name in ("hpBuff", "buffedHp")
    )
    out = subprocess.run(["node", "-e", funcs + f"\nconsole.log(JSON.stringify({call}));"],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_hp_buff_parsing_and_maths():
    assert run('hpBuff({value: "1.6"})') == 1.6
    assert run('hpBuff({value: "3x"})') == 3
    assert run('hpBuff({value: " 1.8 "})') == 1.8
    assert run('hpBuff({value: ""})') is None
    assert run('hpBuff({value: "abc"})') is None
    assert run('hpBuff({value: "0"})') is None
    assert run("buffedHp(50000, 1.6)") == 80000
    assert run("buffedHp(33333, 3)") == 99999
    assert run("buffedHp(50000, null)") == 50000
    assert run("buffedHp(null, 2)") is None


def test_hp_buff_wiring():
    assert "teamField(loopingHpLabel, loopingHpInput)" in APP
    assert "teamField(largerHpLabel, largerHpInput)" in APP
    assert "buffedHp(raw, largerBuff ?? loopingBuff)" in APP
    assert 'return result === "Larger shield needed" ? `${largerWhat} needed` : result;' in APP
