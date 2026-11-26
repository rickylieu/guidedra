from pathlib import Path

CSS = (Path(__file__).parents[1] / "site" / "style.css").read_text(encoding="utf-8")


def test_team_risk_is_yellow():
    block = CSS.split("/* team attributes */", 1)[1]
    assert "#ffc53d" in block
    assert "#ff4d4f" not in block
