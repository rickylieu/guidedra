"""Merge annotated source records for one dungeon."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from glossary import (
    annotate_record,
    english_trait,
    extract_details,
    extract_tags,
    is_critical,
)
from rules import apply_rules


PRIMARY_ORDER = ("gamewith", "appmedia", "altema", "game8")
FILL_ORDER = ("gamewith", "appmedia", "altema", "game8")
PART_NAMES = {"部位": "Part", "翼": "Wing", "聖鳥": "Holy bird"}
ROULETTE_ORB_COLORS = frozenset(
    {"Fire", "Water", "Wood", "Light", "Dark", "Heart", "Jammer", "Bomb"}
)


def _consolidate_roulette_variants(
    variants: dict[
        tuple[tuple[str, str | None], tuple[str, ...]], set[str]
    ],
) -> dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]:
    consolidated = {key: set(sources) for key, sources in variants.items()}
    for (when_key, details), sources in list(consolidated.items()):
        if ("Bottom row" in details) == ("6 orbs" in details):
            continue
        counterpart_location = "6 orbs" if "Bottom row" in details else "Bottom row"
        base_details = tuple(
            detail for detail in details if detail not in {"Bottom row", "6 orbs"}
        )
        counterpart_key = (
            when_key,
            (*base_details, counterpart_location),
        )
        if counterpart_key not in consolidated:
            continue
        canonical_key = (
            when_key,
            (*base_details, "Bottom row", "6 orbs"),
        )
        merged_sources = sources | consolidated[counterpart_key]
        consolidated.pop((when_key, details), None)
        consolidated.pop(counterpart_key, None)
        consolidated[canonical_key] = (
            consolidated.get(canonical_key, set()) | merged_sources
        )

    def specificity(color_set: frozenset[str] | None) -> int:
        return (
            len(color_set)
            if color_set is not None
            else len(ROULETTE_ORB_COLORS) + 1
        )

    while True:
        groups: dict[
            tuple[tuple[str, str | None], tuple[str, ...]],
            list[
                tuple[
                    tuple[tuple[str, str | None], tuple[str, ...]],
                    frozenset[str] | None,
                ]
            ],
        ] = defaultdict(list)
        for key in consolidated:
            when_key, details = key
            color_detail = next(
                (
                    detail
                    for detail in details
                    if detail == "All colors"
                    or (
                        set(detail.split(", ")) <= ROULETTE_ORB_COLORS
                        and detail.split(", ")[0] in ROULETTE_ORB_COLORS
                    )
                ),
                None,
            )
            if color_detail is None:
                continue
            color_set = (
                None
                if color_detail == "All colors"
                else frozenset(color_detail.split(", "))
            )
            base_details = tuple(
                detail for detail in details if detail != color_detail
            )
            groups[(when_key, base_details)].append((key, color_set))

        merged_subset = False
        for variants_in_group in groups.values():
            for source_key, source_colors in variants_in_group:
                candidates = []
                for target_key, target_colors in variants_in_group:
                    if target_key == source_key:
                        continue
                    if target_colors is None:
                        includes_source = source_colors is not None
                    else:
                        includes_source = (
                            source_colors is not None
                            and source_colors <= target_colors
                        )
                    if includes_source:
                        candidates.append((target_key, target_colors))
                if not candidates:
                    continue

                smallest_size = min(specificity(colors) for _, colors in candidates)
                nearest = [
                    key
                    for key, colors in candidates
                    if specificity(colors) == smallest_size
                ]
                if len(nearest) != 1:
                    continue
                target_key = nearest[0]
                consolidated[target_key].update(consolidated.pop(source_key))
                merged_subset = True
                break
            if merged_subset:
                break
        if not merged_subset:
            break
    return consolidated


def merge_dungeon(
    manifest_entry: dict[str, Any],
    source_records: dict[str, dict[str, Any]],
    card_names: dict[str, str],
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    if not source_records:
        raise ValueError(f"{manifest_entry['slug']}: no saved source pages were found")

    records = {name: annotate_record(record) for name, record in source_records.items()}
    requested_primary = manifest_entry.get("primary")
    if requested_primary:
        if requested_primary not in records:
            raise ValueError(
                f"{manifest_entry['slug']}: primary source {requested_primary!r} has no saved page"
            )
        primary = requested_primary
    else:
        primary = next(name for name in PRIMARY_ORDER if name in records)

    diagnostics: dict[str, list[Any]] = {
        "untagged_lines": [],
        "unmatched_enemies": [],
        "unnamed_cards": [],
        "hp_disagreements": [],
        "hit_disagreements": [],
        "single_source_tags": [],
        "must_counter_misses": [],
        "untranslated_rules": [],
        "untranslated_parts": [],
        "untranslated_traits": [],
    }

    floor_maps = {
        source: {floor.get("number"): floor for floor in record.get("floors", [])}
        for source, record in records.items()
    }
    floor_keys = list(floor_maps[primary])
    for source, floors in floor_maps.items():
        for number in floors:
            if number not in floor_keys:
                floor_keys.append(number)

    merged_floors: list[dict[str, Any]] = []
    for number in floor_keys:
        source_floors = {
            source: floors[number]
            for source, floors in floor_maps.items()
            if number in floors
        }
        primary_floor = source_floors.get(primary, {})
        primary_enemies = primary_floor.get("enemies", [])
        matched: dict[int, dict[str, dict[str, Any]]] = {
            index: {} for index in range(len(primary_enemies))
        }

        for source, floor in source_floors.items():
            if source == primary:
                continue
            matches, unmatched_primary, unmatched_other = _match_enemies(
                primary_enemies, floor.get("enemies", [])
            )
            for index, enemy in matches.items():
                matched[index][source] = enemy
            for enemy in unmatched_primary:
                diagnostics["unmatched_enemies"].append(
                    {
                        "source": source,
                        "floor": number,
                        "name_jp": enemy.get("name_jp", ""),
                        "message": "primary enemy has no matching enemy",
                    }
                )
            for enemy in unmatched_other:
                diagnostics["unmatched_enemies"].append(
                    {
                        "source": source,
                        "floor": number,
                        "name_jp": enemy.get("name_jp", ""),
                        "message": "source enemy has no matching primary enemy",
                    }
                )

        tags_by_source: dict[str, set[str]] = defaultdict(set)
        details_by_tag: dict[str, list[str]] = defaultdict(list)
        variants_by_tag: dict[
            str, dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]
        ] = defaultdict(lambda: defaultdict(set))
        for source, floor in source_floors.items():
            for enemy in floor.get("enemies", []):
                timing_kinds = {
                    action.get("timing_kind") for action in enemy.get("actions", [])
                }
                has_puzzle_test = (
                    "lesson_pass" in timing_kinds
                    or "lesson_fail" in timing_kinds
                    or {"combo_ge", "combo_le"} <= timing_kinds
                )
                action_interval = _action_interval(enemy)
                for action in enemy.get("actions", []):
                    action_tags = action.get("tags", [])
                    tags_by_source[source].update(action_tags)
                    details = [
                        detail
                        for detail in action.get("details", [])
                        if not detail.startswith("at ×")
                    ]
                    detail_text = ", ".join(details)
                    when_key = _semantic_timing(
                        action, has_puzzle_test, action_interval
                    )
                    for tag in action_tags:
                        variants_by_tag[tag][(when_key, tuple(details))].add(source)
                        if detail_text:
                            if detail_text not in details_by_tag[tag]:
                                details_by_tag[tag].append(detail_text)
                    if not action.get("text") and action.get("text_jp"):
                        diagnostics["untagged_lines"].append(
                            {
                                "source": source,
                                "floor": number,
                                "card": enemy.get("card"),
                                "enemy_jp": enemy.get("name_jp", ""),
                                "text_jp": action.get("text_jp", ""),
                            }
                        )
                for trait in enemy.get("traits_jp", []):
                    trait_tags = extract_tags(trait)
                    tags_by_source[source].update(trait_tags)
                    for tag in trait_tags:
                        for detail in extract_details(trait):
                            if detail not in details_by_tag[tag]:
                                details_by_tag[tag].append(detail)
                    if english_trait(trait) is None:
                        diagnostics["untranslated_traits"].append(
                            {
                                "source": source,
                                "floor": number,
                                "card": enemy.get("card"),
                                "enemy_jp": enemy.get("name_jp", ""),
                                "text_jp": trait,
                            }
                        )

        if manifest_entry["slug"] == "tenkyu-challenge" and number == 3:
            for tags in tags_by_source.values():
                tags.discard("Invulnerable")

        all_tag_names = set().union(*tags_by_source.values()) if tags_by_source else set()
        floor_tags = []
        for tag in sorted(all_tag_names):
            sources = sorted(source for source, tags in tags_by_source.items() if tag in tags)
            details = details_by_tag.get(tag, [])
            details = [
                detail
                for detail in details
                if not any(
                    other.startswith(f"{detail}, ")
                    for other in details
                    if detail.startswith("for ")
                )
            ]
            variants = variants_by_tag.get(tag, {})
            for (when_key, variant_details), variant_sources in list(variants.items()):
                if when_key != ("puzzle_pass", None):
                    continue
                matching_keys = [
                    key
                    for key in variants
                    if key[0][0] == "puzzle_pass"
                    and key[0][1] is not None
                    and key[1] == variant_details
                ]
                if len(matching_keys) == 1:
                    variants[matching_keys[0]].update(variant_sources)
                    del variants[(when_key, variant_details)]
            if tag == "Roulette":
                variants = _consolidate_roulette_variants(variants)
            floor_tags.append(
                {
                    "name": tag,
                    "critical": is_critical(tag),
                    "sources": sources,
                    "details": details,
                    "variants": [
                        {
                            "when": _semantic_timing_label(when_key),
                            "details": list(variant_details),
                            "sources": sorted(variant_sources),
                        }
                        for (when_key, variant_details), variant_sources in sorted(
                            variants.items()
                        )
                    ],
                }
            )
            if len(sources) == 1:
                diagnostics["single_source_tags"].append(
                    {"floor": number, "name": tag, "source": sources[0]}
                )

        enemy_items = []
        for index, primary_enemy in enumerate(primary_enemies):
            candidates = matched[index]
            ordered_candidates = [
                (source, candidates[source])
                for source in FILL_ORDER
                if source in candidates
            ]
            enemy = dict(primary_enemy)
            for field in ("card", "hp", "defense", "parts"):
                if _is_missing(enemy.get(field)):
                    for _, candidate in ordered_candidates:
                        value = candidate.get(field)
                        if not _is_missing(value):
                            enemy[field] = value
                            break

            card = enemy.get("card")
            english_name = card_names.get(str(card)) if card is not None else None
            if not english_name:
                diagnostics["unnamed_cards"].append(
                    {
                        "source": primary,
                        "floor": number,
                        "card": card,
                        "name_jp": enemy.get("name_jp", ""),
                    }
                )
            translated_parts = []
            for part in enemy.get("parts", []):
                name_jp = part.get("name_jp", "")
                name = PART_NAMES.get(name_jp)
                if not name:
                    diagnostics["untranslated_parts"].append(
                        {
                            "source": primary,
                            "floor": number,
                            "card": card,
                            "enemy_jp": enemy.get("name_jp", ""),
                            "name_jp": name_jp,
                        }
                    )
                    name = name_jp
                translated_parts.append({**part, "name": name})

            enemy_items.append(
                {
                    "name": english_name or enemy.get("name_jp", ""),
                    "name_jp": enemy.get("name_jp", ""),
                    "card": card,
                    "hp": enemy.get("hp"),
                    "defense": enemy.get("defense"),
                    "parts": translated_parts,
                    "traits": [
                        trait
                        for item in enemy.get("traits_jp", [])
                        if (trait := english_trait(item)) is not None
                    ],
                    "actions": [
                        {
                            "when": action.get("when", "Unknown timing"),
                            "timing_kind": action.get("timing_kind"),
                            "text": action.get("text", ""),
                            "tags": action.get("tags", []),
                            "hit": action.get("hit"),
                            "enraged": action.get("enraged", False),
                            "details": action.get("details", []),
                            "text_jp": action.get("text_jp", ""),
                            "timing_jp": action.get("timing_jp", ""),
                            "order": action.get("order"),
                            "source": primary,
                        }
                        for action in enemy.get("actions", [])
                    ],
                }
            )

            for source, candidate in candidates.items():
                left, right = enemy.get("hp"), candidate.get("hp")
                if left is not None and right is not None and _differs_over_one_percent(left, right):
                    diagnostics["hp_disagreements"].append(
                        {
                            "floor": number,
                            "source": source,
                            "name_jp": enemy.get("name_jp", ""),
                            "primary_hp": left,
                            "source_hp": right,
                        }
                    )

        appear = primary_floor.get("appear")
        if appear is None:
            appear = next(
                (floor.get("appear") for floor in source_floors.values() if floor.get("appear") is not None),
                None,
            )
        invade_floor_numbers = sorted(
            {
                floor_number
                for floor in source_floors.values()
                for floor_number in floor.get("invade_floors", [])
            }
        )
        merged_floors.append(
            {
                "number": number,
                "invade_floors": invade_floor_numbers,
                "appear": appear,
                "one_of": bool(appear == 1 and len(enemy_items) > 1),
                "halves_max_hp": "Max HP halved" in all_tag_names,
                "tags": floor_tags,
                "enemies": enemy_items,
            }
        )

    for number in floor_keys:
        per_source_max = {}
        for source, floor_map in floor_maps.items():
            floor = floor_map.get(number)
            hits = [
                action["hit"]
                for enemy in floor.get("enemies", [])
                for action in enemy.get("actions", [])
                if action.get("hit") is not None
            ] if floor else []
            if hits:
                per_source_max[source] = max(hits)
        values = list(per_source_max.values())
        base = per_source_max.get(primary, values[0] if values else None)
        if base is not None and any(
            _differs_over_one_percent(base, value)
            for source, value in per_source_max.items()
            if source != primary
        ):
            diagnostics["hit_disagreements"].append(
                {"floor": number, "hits_by_source": per_source_max}
            )

    primary_rules = records[primary].get("rules", {})
    rules = {
        "battles": primary_rules.get("battles"),
        "stamina": primary_rules.get("stamina"),
        "lines_jp": primary_rules.get("lines_jp", []),
        "notes": [],
    }
    merged = {
        "slug": manifest_entry["slug"],
        "name_en": manifest_entry["name_en"],
        "name_jp": manifest_entry["name_jp"],
        "primary": primary,
        "rules": rules,
        "floors": merged_floors,
    }
    apply_rules(merged, records, diagnostics)
    diagnostics["unnamed_cards"].sort(
        key=lambda item: (item["source"], item["floor"] or 0, item["card"] or 0)
    )
    diagnostics["untranslated_parts"].sort(
        key=lambda item: (
            item["source"],
            item["floor"] or 0,
            item["card"] or 0,
            item["name_jp"],
        )
    )
    return merged, diagnostics


def _action_interval(enemy: dict[str, Any]) -> int:
    for trait in enemy.get("traits_jp", []):
        match = re.search(r"(\d+)\s*ターン行動", trait)
        if match:
            return int(match.group(1))
    return 1


def _semantic_timing(
    action: dict[str, Any],
    has_puzzle_test: bool,
    action_interval: int,
) -> tuple[str, str | None]:
    kind = action.get("timing_kind")
    when = action.get("when", "Unknown timing")
    if kind in {"lesson_pass", "after_lesson"}:
        return "puzzle_pass", None
    if kind == "combo_ge" and has_puzzle_test:
        match = re.search(r"If (\d+)\+ combos", when)
        return "puzzle_pass", match.group(1) if match else None
    if kind == "first_action":
        return "action", "1"
    if kind == "sequence":
        order = action.get("order")
        if order is not None and action_interval == 1:
            return "action", str(order)
    if kind in {"nth_action", "turn"}:
        match = re.search(r"(?:Action|Turn) (\d+)", when)
        if match:
            if kind == "nth_action" or action_interval == 1:
                return "action", match.group(1)
            return "turn", match.group(1)
    return "label", when


def _semantic_timing_label(key: tuple[str, str | None]) -> str:
    kind, value = key
    if kind == "puzzle_pass":
        return f"Puzzle test passed ({value}+ combos)" if value else "Puzzle test passed"
    if kind == "action":
        return f"Action {value}"
    if kind == "turn":
        return f"Turn {value}"
    return str(value)


def _is_missing(value: Any) -> bool:
    return value is None or value == []


def _differs_over_one_percent(first: int, second: int) -> bool:
    return abs(first - second) > abs(first) * 0.01


def _match_enemies(
    primary: list[dict[str, Any]], source: list[dict[str, Any]]
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    matches: dict[int, dict[str, Any]] = {}
    used: set[int] = set()

    for index, enemy in enumerate(primary):
        card = enemy.get("card")
        if card is None:
            continue
        for other_index, candidate in enumerate(source):
            if other_index not in used and candidate.get("card") == card:
                matches[index] = candidate
                used.add(other_index)
                break

    if len(primary) == len(source):
        for index, enemy in enumerate(primary):
            if index in matches:
                continue
            candidate = source[index]
            if index in used:
                continue
            if enemy.get("card") is None or candidate.get("card") is None:
                matches[index] = candidate
                used.add(index)

    unmatched_primary = [
        enemy for index, enemy in enumerate(primary) if index not in matches
    ]
    unmatched_source = [
        enemy for index, enemy in enumerate(source) if index not in used
    ]
    return matches, unmatched_primary, unmatched_source
