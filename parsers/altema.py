"""Parser for the saved Altema Tenkyu Challenge guide."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from glossary import parse_japanese_number
from parsers.common import (
    action_order,
    cell_events,
    cell_text,
    clean_monster_name,
    image_alt,
    image_card_number,
    image_url,
    is_floor_label,
    is_type_icon,
    invade_floors,
    make_floor,
    must_counter_lists,
    parse_dungeon_name,
    parse_html,
)


EXPECTED_HEADER = "フロア | モンスター | 先制行動と注意点"


def _floor_table(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        headers = [
            cell_text(cell)
            for cell in first_row.find_all(["th", "td"], recursive=False)
        ]
        if headers == ["フロア", "モンスター", "先制行動と注意点"]:
            return table
    raise ValueError(f"altema: floor table header not found: {EXPECTED_HEADER}")


def _enemy(cell: Tag) -> dict[str, Any]:
    candidates = [
        img
        for img in cell.find_all("img")
        if not img.find_parent("noscript") and image_url(img) and not is_type_icon(img)
    ]
    monster = next((img for img in candidates if image_card_number(img) is not None), None)
    if monster is None:
        monster = candidates[0] if candidates else None
    return {
        "card": image_card_number(monster) if monster else None,
        "name_jp": clean_monster_name(image_alt(monster)) if monster else "",
        "hp": None,
        "defense": None,
        "parts": [],
        "traits_jp": [],
        "actions": [],
    }


def _line_text(item: Tag) -> str:
    return " ".join(
        text for kind, text in cell_events(item) if kind in {"text", "text_indent"}
    )


def _trait(text: str) -> str | None:
    normalized = re.sub(r"\s+", "", text)
    if normalized == "根性":
        return "根性"
    if re.fullmatch(r"超根性[（(][^）)]*[）)]", normalized):
        return normalized
    if re.fullmatch(r"\d+ターン行動", normalized):
        return normalized
    return None


def _actions(cell: Tag, floor: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    actions: list[dict[str, Any]] = []
    traits: list[str] = []
    timing = ""

    for item in cell.find_all("li"):
        if item.find("hr"):
            header = item.find("span", class_="b")
            if header:
                timing = " ".join(header.stripped_strings)
                continue

        text = _line_text(item)
        if not text:
            continue
        if text.startswith("※"):
            if "乱入" in text:
                floor["invade_floors"] = list(
                    dict.fromkeys(floor["invade_floors"] + invade_floors(text))
                )
            continue
        if re.fullmatch(r"\d+体出現", text):
            floor["appear"] = int(re.match(r"\d+", text).group())
            continue
        trait = _trait(text)
        if trait:
            traits.append(trait)
            continue
        if text == "拡大する":
            continue
        if text.startswith("┗") and actions:
            actions[-1]["text_jp"] += " " + text[1:].strip()
            continue

        actions.append(
            {
                "timing_jp": timing,
                "text_jp": text,
                "order": action_order(text),
            }
        )

    return actions, list(dict.fromkeys(traits))


def _rules(soup: BeautifulSoup) -> dict[str, Any]:
    battles = None
    stamina = None
    lines: list[str] = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) < 2:
                continue
            label = cell_text(cells[0])
            value = cell_text(cells[1])
            if label == "バトル数":
                battles = parse_japanese_number(value)
            elif label == "スタミナ":
                stamina = parse_japanese_number(value)
            elif label == "ルール":
                lines.extend(text for kind, text in cell_events(cells[1]) if kind == "text")
    return {
        "battles": battles,
        "stamina": stamina,
        "lines_jp": list(dict.fromkeys(lines)),
    }


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
            raise ValueError("altema: encountered an enemy row before the first floor")

        enemy = _enemy(enemy_cell)
        actions, traits = _actions(action_cell, current_floor)
        enemy["actions"] = actions
        enemy["traits_jp"] = traits
        current_floor["enemies"].append(enemy)

    must, recommended = must_counter_lists(soup)
    return {
        "source": "altema",
        "dungeon_jp": parse_dungeon_name(soup),
        "rules": _rules(soup),
        "must_counter_jp": must,
        "recommended_jp": recommended,
        "floors": floors,
    }
