from pathlib import Path

SITE = Path(__file__).parents[1] / "site"


def test_team_inputs_in_own_panel():
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert '"team-panel"' in app
    assert "teamField(teamHpLabel, teamHpInput)" in app
    assert "teamField(leaderLabel, leaderInput)" in app
    assert "teamField(helperLabel, helperInput)" in app
    assert "teamPanel.append(teamFields, effectiveHpNote)" in app
    css = (SITE / "style.css").read_text(encoding="utf-8")
    for rule in (".team-panel {", ".team-fields {", ".team-field {"):
        assert rule in css
