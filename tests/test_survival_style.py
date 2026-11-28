from pathlib import Path

SITE = Path(__file__).parents[1] / "site"


def test_survival_labels_styled():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert "alert === \"Can't survive\"" in app
    assert "\"cant-survive\"" in app
    assert "alert === \"Larger shield needed\"" in app
    assert "\"larger-shield\"" in app
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert ".hit-chip.cant-survive {" in css
    assert ".hit-chip.larger-shield {" in css
