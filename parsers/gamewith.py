"""Parser for the saved GameWith Tenkyu Challenge guide."""

from __future__ import annotations

import re
from typing import Any
from bs4 import BeautifulSoup, NavigableString, Tag

from glossary import parse_japanese_number
from parsers.common import (
    actions_from_cell,
    cell_events,
    cell_text,
    clean_monster_name,
    image_alt,
    image_card_number,
    image_url,
    invade_floors,
    is_floor_label,
    is_type_icon,
    make_floor,
    must_counter_lists,
    parse_dungeon_name,
    parse_html,
)


EXPECTED_HEADER = "(blank) | 敵 | 先制行動と特性"


def _floor_table(soup: BeautifulSoup) -> Tag:
    heading = soup.find("h3", id="floor")
    chart = heading.find_next("div", class_="pad-chart") if heading else None
    table = chart.find("table") if chart else None
    if table:
        first_row = table.find("tr")
        headers = (
            [cell_text(cell) for cell in first_row.find_all(["th", "td"], recursive=False)]
            if first_row
            else []
        )
        if headers == ["", "敵", "先制行動と特性"]:
            return table
    raise ValueError(f"gamewith: floor table header not found: {EXPECTED_HEADER}")


def _enemy(cell: Tag) -> dict[str, Any]:
    candidates = [
        img
        for img in cell.find_all("img")
        if not img.find_parent("noscript") and image_url(img) and not is_type_icon(img)
    ]
    monster = next((img for img in candidates if image_card_number(img) is not None), None)
    if monster is None:
        monster = candidates[0] if candidates else None

    text = cell_text(cell)
    hp = _parse_stat(text, "HP")
    defense = _parse_stat(text, "防御")
    parts = _parse_parts(cell)
    name = clean_monster_name(image_alt(monster)) if monster else ""
    if name.startswith("パズドラの"):
        name = name[len("パズドラの") :].strip()

    return {
        "card": image_card_number(monster) if monster else None,
        "name_jp": name,
        "hp": hp,
        "defense": defense,
        "parts": parts,
        "traits_jp": [],
        "actions": [],
    }


def _parse_stat(text: str, label: str) -> int | None:
    match = re.search(
        rf"{label}\s*[:：]?\s*([\d,]+(?:\.\d+)?(?:兆|億|万)?)",
        text,
    )
    return parse_japanese_number(match.group(1)) if match else None


def _text_after_hr(cell: Tag) -> str:
    separator = cell.find("hr")
    if not separator:
        return ""
    pieces: list[str] = []
    for sibling in separator.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "hr":
            break
        if isinstance(sibling, Tag) and sibling.name in {"br", "img", "noscript"}:
            continue
        if isinstance(sibling, NavigableString):
            pieces.append(str(sibling))
        elif isinstance(sibling, Tag):
            pieces.append(sibling.get_text(" ", strip=True))
    return " ".join(pieces)


def _parse_parts(cell: Tag) -> list[dict[str, Any]]:
    text = _text_after_hr(cell)
    parts: list[dict[str, Any]] = []
    for match in re.finditer(r"([^\s:：]+)\s*[:：]\s*([\d,]+(?:\.\d+)?(?:兆|億|万)?)", text):
        hp = parse_japanese_number(match.group(2))
        if hp is not None:
            parts.append({"name_jp": match.group(1), "hp": hp})
    return parts


def _rules(soup: BeautifulSoup) -> dict[str, Any]:
    notes = []
    for container in soup.select("div.pad-note"):
        for table in container.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"], recursive=False)
                if len(cells) >= 2 and cell_text(cells[0]) == "ルール":
                    notes.extend(
                        text
                        for kind, text in cell_events(cells[1])
                        if kind in {"text", "text_indent"}
                    )
    return {"battles": None, "stamina": None, "lines_jp": list(dict.fromkeys(notes))}


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
            raise ValueError("gamewith: encountered an enemy row before the first floor")

        enemy = _enemy(enemy_cell)
        actions, traits = actions_from_cell(action_cell, "gamewith")
        enemy["actions"] = actions
        enemy["traits_jp"] = traits
        current_floor["enemies"].append(enemy)
        if current_floor["number"] is None:
            current_floor["invade_floors"] = list(
                dict.fromkeys(current_floor["invade_floors"] + invade_floors(cell_text(action_cell)))
            )

    footer = soup.select_one("div.pad-footer")
    must, recommended = must_counter_lists(soup, footer)
    return {
        "source": "gamewith",
        "dungeon_jp": parse_dungeon_name(soup),
        "rules": _rules(soup),
        "must_counter_jp": must,
        "recommended_jp": recommended,
        "floors": floors,
    }
