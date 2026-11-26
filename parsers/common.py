"""Shared HTML and Japanese dungeon-page parsing helpers."""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from glossary import normalize_text


ORBS = ("お邪魔", "回復", "火", "水", "木", "光", "闇", "爆弾")
ORB_DETAILS = {
    "火": "火",
    "水": "水",
    "木": "木",
    "光": "光",
    "闇": "闇",
    "回復": "回復",
    "お邪魔": "お邪魔",
    "爆弾": "爆弾",
}
_CIRCLED_ORDERS = dict(zip("①②③④⑤⑥⑦⑧⑨", range(1, 10)))
_ONE_SHOT_NOTE = re.compile(r"ワンパン必須|1ターンで倒す")


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_dungeon_name(soup: BeautifulSoup) -> str:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if not title:
        heading = soup.find("h1")
        title = heading.get_text(" ", strip=True) if heading else ""
    title = re.sub(r"\s+", " ", title).strip().replace("【パズドラ】", "")
    title = re.split(r"の攻略", title, maxsplit=1)[0].strip()
    if not title:
        raise ValueError("could not find the dungeon title")
    return title


def image_url(img: Tag) -> str | None:
    for attribute in ("data-original", "data-lazy-src", "data-src", "src"):
        candidate = img.get(attribute)
        if not candidate:
            continue
        url = str(candidate).strip()
        if _is_placeholder(url):
            continue
        return url
    return None


def _is_placeholder(url: str) -> bool:
    lower = url.lower()
    return (
        lower.startswith("data:image")
        or "1x1" in lower
        or "pixel.gif" in lower
        or "blank.gif" in lower
    )


def image_filename(img: Tag) -> str | None:
    url = image_url(img)
    if not url:
        return None
    return PurePosixPath(unquote(urlparse(url).path)).name or None


def image_card_number(img: Tag) -> int | None:
    url = image_url(img)
    if not url:
        return None
    path = unquote(urlparse(url).path)
    match = re.search(
        r"/(?:icon/|monster/(?:i_)?|gacha/)(?:i_)?(\d+)\.(?:png|jpe?g|webp)$",
        path,
        re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def image_alt(img: Tag) -> str:
    return normalize_text(str(img.get("alt", "")))


def is_type_icon(img: Tag) -> bool:
    alt = image_alt(img)
    filename = image_filename(img) or ""
    return alt.endswith("タイプ") or bool(re.fullmatch(r"t[1-8]\.\w+", filename))


def orb_token(alt: str) -> str | None:
    text = normalize_text(alt)
    match = re.fullmatch(
        r"(お邪魔|回復|猛毒|毒|火|水|木|光|闇|爆弾)(?:ドロップ)?(?:目覚め)?",
        text,
    )
    return f"[{match.group(1)}]" if match else None


def orb_image_token(img: Tag) -> str | None:
    token = orb_token(image_alt(img))
    if token:
        return token
    filename = (image_filename(img) or "").lower()
    orb_by_filename = {
        "fire.png": "[火]",
        "water.png": "[水]",
        "tree.png": "[木]",
        "light.png": "[光]",
        "dark.png": "[闇]",
        "heart.png": "[回復]",
        "ojama.png": "[お邪魔]",
        "bomb.png": "[爆弾]",
    }
    return orb_by_filename.get(filename.removeprefix("drop_"))


def cell_events(cell: Tag) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        raw = "".join(buffer)
        indented = raw.startswith("　")
        text = _normalize_cell_text(raw)
        buffer.clear()
        if text:
            events.append(("text_indent" if indented else "text", text))

    def visit(node: Any) -> None:
        if isinstance(node, NavigableString):
            buffer.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "noscript":
            return
        if node.name == "details":
            flush()
            for child in node.children:
                visit(child)
            flush()
            return
        if node.name in {"br", "hr", "li", "p"}:
            flush()
            return
        if node.name == "img":
            token = orb_image_token(node)
            if token:
                buffer.append(token)
            elif is_type_icon(node):
                # A type icon inside an open 【…】 header names the type,
                # e.g. 【(神タイプ icon)半減】. Everywhere else it is dropped.
                alt = image_alt(node)
                pending = "".join(buffer)
                if alt.endswith("タイプ") and pending.rfind("【") > pending.rfind("】"):
                    buffer.append(alt)
            return
        classes = node.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()
        if "a-label-tag" in classes:
            flush()
            label = normalize_text(node.get_text(" ", strip=True))
            if label:
                events.append(("label", label))
            return
        for child in node.children:
            visit(child)

    for child in cell.children:
        visit(child)
    flush()
    return events


def _normalize_cell_text(value: str) -> str:
    circles = "①②③④⑤⑥⑦⑧⑨"
    protected = value
    for index, character in enumerate(circles, start=1):
        protected = protected.replace(character, f"\ue000{index}\ue001")
    protected = normalize_text(protected)
    for index, character in enumerate(circles, start=1):
        protected = protected.replace(f"\ue000{index}\ue001", character)
    return protected


def cell_text(cell: Tag) -> str:
    return normalize_text(
        " ".join(text for kind, text in cell_events(cell) if kind in {"text", "text_indent"})
    )


def floor_number(value: str) -> int | None:
    text = unicodedata.normalize("NFKC", value).strip()
    patterns = (
        r"\bB\s*(\d+)\b",
        r"\b(\d+)\s*F\b",
        r"(\d+)\s*階",
        r"バトル\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def is_floor_label(value: str) -> bool:
    text = unicodedata.normalize("NFKC", value).strip()
    return "乱入" in text or floor_number(text) is not None


def appear_count(value: str) -> int | None:
    match = re.search(r"(\d+)\s*体(?:出現)?", unicodedata.normalize("NFKC", value))
    return int(match.group(1)) if match else None


def invade_floors(value: str) -> list[int]:
    text = unicodedata.normalize("NFKC", value)
    item = r"(?:B\s*)?\d{1,2}(?:\s*F)?"
    separator = r"\s*(?:or|[/・,、])\s*"
    run = rf"(?<![A-Za-z0-9]){item}(?:{separator}{item})*(?![A-Za-z0-9])"
    floors: list[int] = []
    for match in re.finditer(run, text, re.IGNORECASE):
        if not re.search(r"[BF]", match.group(), re.IGNORECASE):
            continue
        floors.extend(int(number) for number in re.findall(r"\d+", match.group()))
    return list(dict.fromkeys(floors))


def action_order(text: str) -> int | None:
    for character, number in _CIRCLED_ORDERS.items():
        if character in text:
            return number
    match = re.match(r"\s*(\d+)[.．、]", normalize_text(text))
    return int(match.group(1)) if match else None


def _trait_from_text(text: str) -> str | None:
    normalized = normalize_text(text).strip("【】[] ")
    if re.fullmatch(r"根性", normalized):
        return "根性"
    if re.fullmatch(
        r"超根性(?:\s*[:：]\s*[^:：\s]+|[（(][^）)]*[）)])?",
        normalized,
    ):
        return normalized
    if re.fullmatch(r"\d+ターン行動", normalized):
        return normalized
    if re.fullmatch(r"(?:\S+?タイプ)*半減", normalized):
        return normalized
    return None


def actions_from_cell(cell: Tag, source: str) -> tuple[list[dict[str, Any]], list[str]]:
    actions: list[dict[str, Any]] = []
    traits: list[str] = []
    timing = ""

    sequence = ""
    pending_order = None

    def set_timing(content: str) -> None:
        nonlocal timing, sequence, pending_order
        numbered = re.fullmatch(r"通常(?:行動|攻撃)\s*([①-⑳]|\d+)", content)
        if sequence and numbered:
            mark = numbered.group(1)
            pending_order = int(mark) if mark.isdecimal() else ord(mark) - 0x245F
            timing = sequence
            return
        sequence = ""
        pending_order = None
        timing = content

    def handle_line(line: str) -> None:
        nonlocal timing, sequence, pending_order
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            return
        if source in {"appmedia", "gamewith"}:
            if line.startswith("※") and re.search(r"順番に.*使用", line):
                sequence = timing = line.lstrip("※ ").strip()
                pending_order = None
                return
            if line.startswith("※") and _ONE_SHOT_NOTE.search(line):
                line = line.lstrip("※ ").strip()
            elif line.startswith("※") or "出現を確認" in line:
                return
        if line.startswith("┗") and actions:
            actions[-1]["text_jp"] += " " + line[1:].strip()
            return

        header = re.fullmatch(r"【([^】]+)】", line)
        if header:
            content = header.group(1).strip()
            trait = _trait_from_text(content)
            if trait:
                traits.append(trait)
            else:
                set_timing(content)
            return

        trait = _trait_from_text(line)
        if trait:
            traits.append(trait)
            return

        if line.startswith("【") and "】" in line:
            prefix, remainder = line.split("】", 1)
            content = prefix[1:].strip()
            trait = _trait_from_text(content)
            if trait:
                traits.append(trait)
            else:
                set_timing(content)
            line = remainder.strip()
            if not line:
                return

        actions.append(
            {
                "timing_jp": timing,
                "text_jp": line,
                "order": pending_order or action_order(line),
            }
        )

    for kind, text in cell_events(cell):
        if kind == "label":
            if source == "game8" and text == "超根性":
                traits.append(text)
                timing = text
                continue
            trait = _trait_from_text(text)
            if trait:
                traits.append(trait)
            else:
                timing = text
            continue
        if kind == "text_indent" and actions:
            actions[-1]["text_jp"] += " " + text
            continue
        for line in text.splitlines() or [text]:
            handle_line(line)

    return actions, list(dict.fromkeys(traits))


def must_counter_lists(
    soup: BeautifulSoup, container: Tag | None = None
) -> tuple[list[str], list[str]]:
    tables = container.find_all("table") if container else soup.find_all("table")
    for table in tables:
        headers = [
            normalize_text(th.get_text(" ", strip=True))
            for th in table.find_all("th")
        ]
        if not any("対策必須" in header for header in headers):
            continue

        must: list[str] = []
        recommended: list[str] = []
        current: list[str] | None = None
        for row in table.find_all("tr"):
            heading = " ".join(
                normalize_text(th.get_text(" ", strip=True))
                for th in row.find_all("th", recursive=False)
            )
            if heading:
                if "対策必須" in heading:
                    current = must
                elif "対策推奨" in heading or "余裕があれば対策" in heading:
                    current = recommended
                else:
                    current = None
                continue
            if current is None:
                continue
            for cell in row.find_all("td", recursive=False):
                text = normalize_text(" ".join(cell.stripped_strings))
                if text:
                    current.append(text)
        return list(dict.fromkeys(must)), list(dict.fromkeys(recommended))

    return [], []


def make_floor(label: str) -> dict[str, Any]:
    number = None if "乱入" in label else floor_number(label)
    return {
        "number": number,
        "invade_floors": [],
        "appear": appear_count(label),
        "enemies": [],
    }


def clean_monster_name(value: str, suffixes: tuple[str, ...] = ("の画像", "_アイコン")) -> str:
    result = normalize_text(value)
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[: -len(suffix)].strip()
    return result