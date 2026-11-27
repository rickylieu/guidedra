from pathlib import Path

SITE = Path(__file__).parents[1] / "site"


def test_each_part_is_its_own_labelled_line():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert "`[Part] ${part.name} HP ${formatNumber(part.hp)}`" in app
    assert ".enemy-part {" in css
