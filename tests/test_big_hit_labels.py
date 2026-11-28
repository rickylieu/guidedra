from pathlib import Path

SITE = Path(__file__).parents[1] / "site"


def test_hit_kind_label_and_big_hit_list():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert '"Big hit · " : "Normal hit · "' in app
    assert "${hitKind}${formatNumber(normalHit)} damage" in app
    assert "function renderBigHitList(container, data)" in app
    assert "renderBigHitList(container, data);" in app
    assert '"No big hits in this dungeon."' in app
    assert "container.hidden = true;" not in app.split("function renderHitSummary")[1].split("const byFloor")[0]
