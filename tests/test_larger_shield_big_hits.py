from pathlib import Path

SITE = Path(__file__).parents[1] / "site"


def test_larger_shield_only_for_big_hits():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert 'return action.severity === "large";' in app
    assert "isBigHit(action) ? largerEffectiveHp : null" in app
    assert "worst.set(floor.label, { damage, floor, big: isBigHit(action), action });" in app
    assert "const useLarger = big && largerEffectiveHp !== null;" in app
    assert "const limit = largerEffectiveHp ?? teamHp;" not in app
