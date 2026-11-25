"""Parser for the saved Game8 Tenkyu Challenge guide."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup, Tag

from parsers.common import (
    actions_from_cell,
    cell_text,
    clean_monster_name,
    image_alt,
    image_url,
    invade_floors,
    is_floor_label,
    make_floor,
    must_counter_lists,
    parse_dungeon_name,
    parse_html,
)


EXPECTED_HEADER = "階層 | 敵キャラ | 注意点・先制行動"


def _floor_table(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        headers = [
            cell_text(cell)
            for cell in first_row.find_all(["th", "td"], recursive=False)
        ]
        if headers == ["階層", "敵キャラ", "注意点・先制行動"]:
            return table
    raise ValueError(f"game8: floor table header not found: {EXPECTED_HEADER}")


def _monster_name(cell: Tag) -> str:
    for img in cell.find_all("img"):
        if img.find_parent("noscript") or not image_url(img):
            continue
        alt = image_alt(img)
        if alt and not alt.endswith("タイプ"):
            return clean_monster_name(alt)
    return ""


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
            raise ValueError("game8: encountered an enemy row before the first floor")

        actions, traits = actions_from_cell(action_cell, "game8")
        current_floor["enemies"].append(
            {
                "card": None,
                "name_jp": _monster_name(enemy_cell),
                "hp": None,
                "defense": None,
                "parts": [],
                "traits_jp": traits,
                "actions": actions,
            }
        )
        if current_floor["number"] is None:
            current_floor["invade_floors"] = list(
                dict.fromkeys(current_floor["invade_floors"] + invade_floors(cell_text(action_cell)))
            )

    must, recommended = must_counter_lists(soup)
    return {
        "source": "game8",
        "dungeon_jp": parse_dungeon_name(soup),
        "rules": {"battles": None, "stamina": None, "lines_jp": []},
        "must_counter_jp": must,
        "recommended_jp": recommended,
        "floors": floors,
    }
