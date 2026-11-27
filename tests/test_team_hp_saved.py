from pathlib import Path

APP = Path(__file__).parents[1] / "site" / "app.js"


def test_redraw_events_do_not_touch_saved_hp():
    app = APP.read_text(encoding="utf-8")
    assert 'teamHpInput.addEventListener("input", (event) => {' in app
    assert "if (event.isTrusted) window.localStorage.removeItem(STORAGE_KEY);" in app
    assert "if (event.isTrusted) window.localStorage.setItem(STORAGE_KEY, teamHpInput.value);" in app
    assert app.count("window.localStorage.removeItem(STORAGE_KEY);") == 1
