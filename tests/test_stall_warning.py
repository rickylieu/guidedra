from pathlib import Path

SITE = Path(__file__).parents[1] / "site"


def test_stalled_floors_are_a_separate_red_line():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert "Your attributes can't damage" not in app
    assert "Can't clear in time:" in app
    assert "skill-plan-stall" in app
    assert ".skill-plan-stall" in css
