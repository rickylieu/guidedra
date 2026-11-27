import json
from pathlib import Path

import pytest

from merge import _fold_unspecified_amounts

RANDOM = ("label", "One at random")
ABSORB = ("for 1 turn", "1 random color")


def test_numbered_folds_into_random():
    out = _fold_unspecified_amounts({
        (RANDOM, ABSORB): {"gamewith"},
        (("action", "1"), ABSORB): {"appmedia", "altema"},
    })
    assert out == {(RANDOM, ABSORB): {"gamewith", "appmedia", "altema"}}


def test_different_details_stay_apart():
    out = _fold_unspecified_amounts({
        (RANDOM, ABSORB): {"gamewith"},
        (("action", "1"), ("for 2 turns",)): {"appmedia"},
    })
    assert len(out) == 2


def test_two_numbered_matches_stay_apart():
    out = _fold_unspecified_amounts({
        (RANDOM, ABSORB): {"gamewith"},
        (("action", "1"), ABSORB): {"appmedia"},
        (("action", "3"), ABSORB): {"altema"},
    })
    assert len(out) == 3


def test_built_floors_have_no_split_random_moves():
    data_dir = Path(__file__).parents[1] / "site" / "data"
    files = [p for p in data_dir.glob("*.json") if not p.name.endswith("-debug.json")]
    checked = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "floors" not in data:
            continue
        checked += 1
        for floor in data["floors"]:
            for tag in floor.get("tags", []):
                seen = {}
                for variant in tag.get("variants", []):
                    key = (tuple(variant.get("details", [])), tuple(variant.get("enemies", [])))
                    seen.setdefault(key, set()).add(variant.get("when", ""))
                for key, whens in seen.items():
                    if "One at random" in whens:
                        assert not any(w.startswith("Action ") for w in whens), (
                            f"{path.name} {floor['label']} {tag['name']}: {sorted(whens)} {key}"
                        )
    if not checked:
        pytest.skip("no built dungeon JSON")
