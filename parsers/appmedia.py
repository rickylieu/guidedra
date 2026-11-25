"""Parser for the saved AppMedia Tenkyu Challenge guide."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from glossary import parse_japanese_number
from parsers.common import (
    actions_from_cell,
    cell_text,
    clean_monster_name,
    image_alt,
    image_card_number,
    image_url,
    invade_floors,
    is_floor_label,
    make_floor,
    must_counter_lists,
    parse_dungeon_name,
    parse_html,
)


EXPECTED_HEADER = "階層 | 出現 | 特性/ギミック"


def _floor_table(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        headers = [
            cell_text(cell)
            for cell in first_row.find_all(["th", "td"], recursive=False)
        ]
        if headers == ["階層", "出現", "特性/ギミック"]:
            return table
    raise ValueError(f"appmedia: floor table header not found: {EXPECTED_HEADER}")


def _images(cell: Tag) -> list[Tag]:
    result: list[Tag] = []
    seen: set[tuple[str, str]] = set()
    for img in cell.find_all("img"):
        if img.find_parent("noscript"):
            continue
        url = image_url(img)
        if not url:
            continue
        identity = (url, image_alt(img))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(img)
    return result


def _enemy(cell: Tag) -> dict[str, Any]:
    images = _images(cell)
    monster_image = next((img for img in images if image_card_number(img) is not None), None)
    if monster_image is None:
        monster_image = next(
            (
                img
                for img in images
                if image_alt(img) and not image_alt(img).endswith("タイプ")
            ),
            None,
        )

    text = cell_text(cell)
    main_text = text.split("【", 1)[0]
    hp = _parse_stat(main_text, "HP")
    defense = _parse_stat(main_text, "防御")
    parts = []
    for match in re.finditer(r"【([^】]+)】\s*HP\s*[:：]?\s*([\d,.]+(?:兆|億|万)?)", text):
        part_hp = parse_japanese_number(match.group(2))
        if part_hp is not None:
            parts.append({"name_jp": match.group(1).strip(), "hp": part_hp})

    name = clean_monster_name(image_alt(monster_image)) if monster_image else ""
    return {
        "card": image_card_number(monster_image) if monster_image else None,
        "name_jp": name,
        "hp": hp,
        "defense": defense,
        "parts": parts,
        "traits_jp": [],
        "actions": [],
    }


def _parse_stat(text: str, label: str) -> int | None:
    match = re.search(rf"{label}\s*[:：]?\s*([\d,.]+(?:兆|億|万)?)", text)
    return parse_japanese_number(match.group(1)) if match else None


def parse(html: str) -> dict[str, Any]:
    soup = parse_html(html)
    table = _floor_table(soup)
    floors: list[dict[str, Any]] = []
    current_floor: dict[str, Any] | None = None

    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["th", "td"], recursive=False)
        floor_cell: Tag | None = None
        if len(cells) >= 3 and is_floor_label(cell_text(cells[0])):
            floor_cell = cells[0]
            enemy_cell, action_cell = cells[-2], cells[-1]
        elif len(cells) >= 2:
            enemy_cell, action_cell = cells[-2], cells[-1]
        else:
            continue

        if floor_cell is not None:
            current_floor = make_floor(cell_text(floor_cell))
            floors.append(current_floor)
        if current_floor is None:
            raise ValueError("appmedia: encountered an enemy row before the first floor")

        enemy = _enemy(enemy_cell)
        actions, traits = actions_from_cell(action_cell, "appmedia")
        enemy["actions"] = actions
        enemy["traits_jp"] = traits
        current_floor["enemies"].append(enemy)

        if current_floor["number"] is None:
            current_floor["invade_floors"] = list(
                dict.fromkeys(current_floor["invade_floors"] + _parse_invade_notes(action_cell))
            )

    must, recommended = must_counter_lists(soup)
    return {
        "source": "appmedia",
        "dungeon_jp": parse_dungeon_name(soup),
        "rules": {"battles": None, "stamina": None, "lines_jp": []},
        "must_counter_jp": must,
        "recommended_jp": recommended,
        "floors": floors,
    }


def _parse_invade_notes(cell: Tag) -> list[int]:
    return invade_floors(cell_text(cell))
