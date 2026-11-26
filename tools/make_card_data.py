"""One-off: build card_names.json and card_elements.json from Mapaler's mon_ja.json.

Download the data once (this is not part of the build):
  curl -L -o raw/mon_ja.json https://raw.githubusercontent.com/Mapaler/PADDashFormation/master/monsters-info/mon_ja.json
Then run:
  python tools/make_card_data.py
Names already in card_names.json are kept, so hand fixes survive a rerun.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "raw" / "mon_ja.json"
NAMES_FILE = ROOT / "card_names.json"
ELEMENTS_FILE = ROOT / "card_elements.json"
ELEMENTS = {0: "Fire", 1: "Water", 2: "Wood", 3: "Light", 4: "Dark"}
PLACEHOLDER = re.compile(r"^\s*(?:\?+|\*+)")
CHECK_CARDS = (10981, 4638, 13548, 14018, 14019)


def iter_cards(data: Any) -> Iterator[dict[str, Any]]:
    if isinstance(data, dict):
        data = data.get("card") or data.get("cards") or list(data.values())
    for card in data:
        if isinstance(card, dict) and isinstance(card.get("id"), int):
            yield card


def english_name(card: dict[str, Any]) -> str | None:
    other = card.get("otLangName")
    name = other.get("en") if isinstance(other, dict) else None
    if not isinstance(name, str) or not name.strip() or PLACEHOLDER.match(name):
        return None
    return name.strip()


def elements(card: dict[str, Any]) -> list[str]:
    attrs = card.get("attrs")
    if not isinstance(attrs, list):
        return []
    return [ELEMENTS[a] for a in attrs if a in ELEMENTS]


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_sorted(path: Path, data: dict[str, Any]) -> None:
    ordered = {key: data[key] for key in sorted(data, key=int)}
    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        raise SystemExit(f"not found: {source} (download it with the curl line at the top)")

    cards = list(iter_cards(json.loads(source.read_text(encoding="utf-8"))))
    if not cards:
        raise SystemExit(f"{source}: no cards with a numeric 'id' found")

    names: dict[str, str] = {}
    card_elements: dict[str, list[str]] = {}
    for card in cards:
        key = str(card["id"])
        name = english_name(card)
        if name:
            names[key] = name
        found = elements(card)
        if found:
            card_elements[key] = found

    if not names or not card_elements:
        sample = next(c for c in cards if c["id"] > 0)
        raise SystemExit(
            f"{source}: found {len(names)} English names and {len(card_elements)} "
            f"element lists. Fields on card {sample['id']}: {sorted(sample)}"
        )

    existing_names = load_existing(NAMES_FILE)
    kept = {k: v for k, v in existing_names.items() if isinstance(v, str) and v.strip()}
    write_sorted(NAMES_FILE, {**names, **kept})

    existing_elements = load_existing(ELEMENTS_FILE)
    write_sorted(ELEMENTS_FILE, {**card_elements, **existing_elements})

    print(f"{len(cards)} cards read")
    print(f"card_names.json: {len(names)} from the data, {len(kept)} kept from before")
    print(f"card_elements.json: {len(card_elements)} cards")
    for number in CHECK_CARDS:
        key = str(number)
        print(f"  {number}: {names.get(key, '(no English name)')} {card_elements.get(key, [])}")


if __name__ == "__main__":
    main()