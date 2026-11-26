from pathlib import Path

CSS = Path(__file__).parents[1] / "site" / "style.css"


def test_enemy_heading_name_right_stats_left():
    css = CSS.read_text(encoding="utf-8")
    block = css.split("/* enemy heading: name right, stats left */", 1)
    assert len(block) == 2, "enemy heading layout rule missing"
    rule = block[1]
    name = rule.split(".enemy-heading h4", 1)[1].split("}", 1)[0]
    stats = rule.split(".enemy-heading .enemy-stats", 1)[1].split("}", 1)[0]
    assert "order: 2" in name and "margin-left: auto" in name
    assert "order: 1" in stats
