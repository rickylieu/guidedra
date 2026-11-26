"""Command-line entry point for parsing and building dungeon guides."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from datetime import date
from typing import Any

from merge import merge_dungeon
from parsers import altema, appmedia, game8, gamewith
from rules import action_hit_severity, floor_label, hit_multiple


PARSERS = {
    "altema": altema,
    "appmedia": appmedia,
    "game8": game8,
    "gamewith": gamewith,
}


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--debug", action="store_true")
    argument_parser.add_argument("slug", nargs="?")
    argument_parser.add_argument("source", choices=sorted(PARSERS), nargs="?")
    args = argument_parser.parse_args()

    manifest_path = Path("dungeons.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.debug:
        if not args.slug or not args.source:
            argument_parser.error("--debug requires a dungeon slug and source name")
        _find_dungeon(manifest, args.slug, argument_parser)
        html_path = Path("raw") / args.slug / f"{args.source}.html"
        if not html_path.is_file():
            argument_parser.error(f"saved page not found: {html_path}")
        record = PARSERS[args.source].parse(html_path.read_text(encoding="utf-8"))
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return

    if args.source:
        argument_parser.error("a source name is only accepted with --debug")
    dungeons = [_find_dungeon(manifest, args.slug, argument_parser)] if args.slug else manifest
    card_names = json.loads(Path("card_names.json").read_text(encoding="utf-8"))
    card_elements = json.loads(Path("card_elements.json").read_text(encoding="utf-8"))
    Path("site/data").mkdir(parents=True, exist_ok=True)
    Path("site/data/card_elements.json").write_text(
        json.dumps(card_elements, separators=(",", ":")), encoding="utf-8"
    )
    sections = []
    built = date.today().isoformat()
    for dungeon in dungeons:
        records = _read_source_records(dungeon)
        merged, diagnostics = merge_dungeon(dungeon, records, card_names)
        sections.append((merged, diagnostics))
        published = _publish_dungeon(dungeon, merged, records, built)
        data_dir = Path("site/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / f"{dungeon['slug']}.json").write_text(
            json.dumps(published, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        debug_published = _publish_dungeon(dungeon, merged, records, built, debug=True)
        (data_dir / f"{dungeon['slug']}-debug.json").write_text(
            json.dumps(debug_published, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    Path("report.md").write_text(_render_report(sections), encoding="utf-8")
    _write_index(manifest, built, {dungeon["slug"] for dungeon in dungeons})
    print("Wrote report.md")


def _find_dungeon(
    manifest: list[dict[str, Any]],
    slug: str,
    argument_parser: argparse.ArgumentParser,
) -> dict[str, Any]:
    for dungeon in manifest:
        if dungeon.get("slug") == slug:
            return dungeon
    argument_parser.error(f"unknown dungeon slug: {slug}")
    raise AssertionError("argparse.error always exits")


def _read_source_records(dungeon: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = {}
    for source, parser in PARSERS.items():
        html_path = Path("raw") / dungeon["slug"] / f"{source}.html"
        if html_path.is_file():
            records[source] = parser.parse(html_path.read_text(encoding="utf-8"))
    return records


def _publish_dungeon(
    entry: dict[str, Any],
    merged: dict[str, Any],
    records: dict[str, dict[str, Any]],
    built: str,
    debug: bool = False,
) -> dict[str, Any]:
    source_names = {
        "appmedia": "AppMedia",
        "game8": "Game8",
        "altema": "Altema",
        "gamewith": "GameWith",
    }
    ordered_sources = [merged["primary"]] + [
        source for source in source_names if source != merged["primary"]
    ]
    sources = [
        {
            "name": source_names[source],
            "url": entry.get("sources", {}).get(source, ""),
        }
        for source in ordered_sources
        if source in records
    ]
    floors = []
    for floor in merged["floors"]:
        enemies = []
        for enemy in floor["enemies"]:
            enrage_multiplier = _enemy_enrage_multiplier(enemy)
            if enrage_multiplier is None and len(floor["enemies"]) == 1:
                enrage_multiplier = _floor_enrage_multiplier(floor)
            enemies.append(
                {
                    "name": enemy["name"],
                    "card": enemy["card"],
                    "hp": enemy["hp"],
                    "defense": enemy["defense"],
                    "parts": [
                        {"name": part["name"], "hp": part["hp"]}
                        for part in enemy["parts"]
                        if part["name"] != part["name_jp"]
                    ],
                    "traits": enemy["traits"],
                    "actions": [
                        {
                            "when": action["when"],
                            "timing_kind": action["timing_kind"],
                            "order": action["order"],
                            "source": source_names.get(action["source"], action["source"]),
                            "text": action["text"],
                            "tags": action["tags"],
                            "details": action["details"],
                            "hit": action["hit"],
                            "normal_hit": normal_hit,
                            "enraged_hit": enraged_hit,
                            "enraged": action.get("enraged", False),
                            "severity": action_hit_severity(
                                action, merged["normal_hit_baseline"]
                            ),
                            "severity_multiple": (
                                hit_multiple(
                                    action["hit"], merged["normal_hit_baseline"]
                                )
                                if action_hit_severity(
                                    action, merged["normal_hit_baseline"]
                                ) == "large"
                                else None
                            ),
                            **(
                                {"untranslated_text_jp": action["text_jp"]}
                                if debug and not action["text"] and action.get("text_jp")
                                else {}
                            ),
                        }
                        for action in enemy["actions"]
                        for normal_hit, enraged_hit in [
                            _enraged_hit_values(action, enrage_multiplier)
                        ]
                    ],
                }
            )
        floors.append(
            {
                "label": floor_label(floor),
                "number": floor["number"],
                "appear": floor["appear"],
                "one_of": floor["one_of"],
                "halves_max_hp": floor["halves_max_hp"],
                "tags": [
                    {
                        **tag,
                        "sources": [source_names.get(source, source) for source in tag["sources"]],
                        "variants": [
                            {
                                **variant,
                                "sources": [
                                    source_names.get(source, source)
                                    for source in variant["sources"]
                                ],
                            }
                            for variant in tag["variants"]
                        ],
                    }
                    for tag in floor["tags"]
                ],
                "enemies": enemies,
            }
        )
    return {
        "slug": entry["slug"],
        "name_en": entry["name_en"],
        "name_jp": entry["name_jp"],
        "built": built,
        "sources": sources,
        "rules": {
            "battles": merged["rules"]["battles"],
            "stamina": merged["rules"]["stamina"],
            "notes": merged["rules"]["notes"],
        },
        "normal_hit_baseline": merged["normal_hit_baseline"],
        "damage_progression": merged["damage_progression"],
        "summary": merged["summary"],
        "floors": floors,
    }


def _enemy_enrage_multiplier(enemy: dict[str, Any]) -> float | None:
    return _unique_enrage_multiplier(
        detail
        for action in enemy.get("actions", [])
        if "Enrage" in action.get("tags", [])
        for detail in action.get("details", [])
    )


def _floor_enrage_multiplier(floor: dict[str, Any]) -> float | None:
    return _unique_enrage_multiplier(
        detail
        for tag in floor.get("tags", [])
        if tag.get("name") == "Enrage"
        for variant in tag.get("variants", [])
        for detail in variant.get("details", [])
    )


def _unique_enrage_multiplier(details: Any) -> float | None:
    multipliers = {
        float(match.group(1))
        for detail in details
        if (match := re.fullmatch(r"[×x](\d+(?:\.\d+)?)", detail))
    }
    return next(iter(multipliers)) if len(multipliers) == 1 else None


def _enraged_hit_values(
    action: dict[str, Any],
    multiplier: float | None,
) -> tuple[int | None, int | None]:
    hit = action.get("hit")
    if (
        hit is None
        or multiplier is None
        or action.get("timing_kind") == "preemptive"
    ):
        return None, None

    if action.get("enraged"):
        recorded_multiplier = next(
            (
                float(match.group(1))
                for detail in action.get("details", [])
                if (match := re.fullmatch(r"at ×(\d+(?:\.\d+)?) ATK", detail))
            ),
            None,
        )
        if recorded_multiplier != multiplier:
            return None, None
        return int(round(hit / multiplier)), hit

    return hit, int(round(hit * multiplier))


def _write_index(
    manifest: list[dict[str, Any]],
    built: str,
    rebuilt_slugs: set[str],
) -> None:
    data_dir = Path("site/data")
    index = []
    for entry in manifest:
        path = data_dir / f"{entry['slug']}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        index.append(
            {
                "slug": entry["slug"],
                "name_en": entry["name_en"],
                "name_jp": entry["name_jp"],
                "built": built if entry["slug"] in rebuilt_slugs else data["built"],
            }
        )
    (data_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _render_report(sections: list[tuple[dict[str, Any], dict[str, list[Any]]]]) -> str:
    output = ["# PAD Dungeon Guide Build Report", ""]
    for dungeon, diagnostics in sections:
        output.extend(
            [
                f"## {dungeon['name_en']}",
                "",
                f"Primary source: {dungeon['primary']}",
                "",
            ]
        )
        _report_list(output, "Actions without English annotation", diagnostics["untagged_lines"], _untagged)
        _report_list(output, "Unmatched enemies", diagnostics["unmatched_enemies"], _unmatched)
        _report_list(output, "Enemies without English names", diagnostics["unnamed_cards"], _unnamed_card)
        _report_list(output, "HP disagreements", diagnostics["hp_disagreements"], _hp_disagreement)
        _report_list(output, "Largest-hit disagreements", diagnostics["hit_disagreements"], _hit_disagreement)
        _report_list(output, "Tags produced by only one source", diagnostics["single_source_tags"], _single_source_tag)
        _report_list(output, "Must-counter entries with no floor tag", diagnostics["must_counter_misses"], _must_counter_miss)
        _report_list(output, "Rule terms without an English mapping", diagnostics["untranslated_rules"], _untranslated_rule)
        _report_list(output, "Enemy traits without an English mapping", diagnostics["untranslated_traits"], _untranslated_trait)
        _report_list(output, "Part names without an English mapping", diagnostics["untranslated_parts"], _untranslated_part)
    return "\n".join(output).rstrip() + "\n"


def _report_list(output: list[str], title: str, items: list[Any], formatter: Any) -> None:
    output.extend([f"### {title}", ""])
    if not items:
        output.extend(["None.", ""])
        return
    output.extend(f"- {formatter(item)}" for item in items)
    output.append("")


def _untagged(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    return (
        f"{item['source']} · {floor} · Card {item.get('card')} "
        f"({item.get('enemy_jp')}): {item['text_jp']}"
    )


def _unmatched(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    return f"{item['source']} · {floor}: {item['name_jp']} ({item['message']})"


def _unnamed_card(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    card = f"Card {item['card']}" if item["card"] is not None else "Unidentified enemy"
    return (
        f"{item['source']} · {floor} · {card}: "
        f"{item['name_jp']}"
    )


def _hp_disagreement(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    return (
        f"{item['source']} · {floor} · {item['name_jp']}: "
        f"primary {item['primary_hp']}, source {item['source_hp']}"
    )


def _hit_disagreement(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    values = ", ".join(f"{source}: {hit}" for source, hit in sorted(item["hits_by_source"].items()))
    return f"{floor}: {values}"


def _single_source_tag(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    return f"{floor}: {item['name']} ({item['source']})"


def _must_counter_miss(item: dict[str, Any]) -> str:
    label = item["tag"] or item["text_jp"]
    return f"{item['source']}: {label} ({item['text_jp']})"


def _untranslated_rule(item: dict[str, Any]) -> str:
    return f"{item['source']}: {item['text_jp']}"


def _untranslated_trait(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    return (
        f"{item['source']} · {floor} · Card {item.get('card')} "
        f"({item['enemy_jp']}): {item['text_jp']}"
    )


def _untranslated_part(item: dict[str, Any]) -> str:
    floor = "Invade" if item["floor"] is None else f"Floor {item['floor']}"
    return (
        f"{item['source']} · {floor} · Card {item.get('card')} "
        f"({item['enemy_jp']}): {item['name_jp']}"
    )


if __name__ == "__main__":
    main()
