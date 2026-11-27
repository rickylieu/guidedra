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
PART_NAMES = {"部位": "Part", "翼": "Wing", "聖鳥": "Holy bird", "左部位": "Left part", "右部位": "Right part"}
ROULETTE_ORB_COLORS = frozenset(
    {"Fire", "Water", "Wood", "Light", "Dark", "Heart", "Jammer", "Bomb"}
)
BOARD_CHANGE_TAGS = frozenset({"Board change", "Full-board change", "Orb change"})


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


def _consolidate_preferred_variants(
    tag: str,
    variants: dict[
        tuple[tuple[str, str | None], tuple[str, ...]], set[str]
    ],
) -> dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]:
    if tag in BOARD_CHANGE_TAGS and variants:
        by_details: dict[
            tuple[str, ...], list[tuple[tuple[str, str | None], tuple[str, ...]]]
        ] = defaultdict(list)
        for key in variants:
            by_details[key[1]].append(key)
        discarded = set()
        for keys in by_details.values():
            priority = {key: _board_change_timing_priority(key[0]) for key in keys}
            highest = max(priority.values())
            if highest > 1:
                discarded.update(key for key in keys if priority[key] < highest)
        variants = {
            key: sources for key, sources in variants.items() if key not in discarded
        }

    if tag in {"Unmatchable", "Attribute absorb"}:
        groups: dict[
            tuple[tuple[str, str | None], tuple[str, ...]],
            list[tuple[tuple[tuple[str, str | None], tuple[str, ...]], bool]],
        ] = defaultdict(list)
        for key in variants:
            timing, details = key
            colors = tuple(detail for detail in details if _is_color_detail(detail))
            base_details = tuple(
                detail for detail in details if not _is_color_detail(detail)
            )
            groups[(timing, base_details)].append((key, bool(colors)))
        for group in groups.values():
            specific = [key for key, has_colors in group if has_colors]
            if len(specific) == 1:
                for key, has_colors in group:
                    if not has_colors:
                        variants.pop(key, None)

    return variants


def _prioritize_puzzle_test_failure(
    variants_by_entity: dict[
        str, dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]
    ],
) -> dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]:
    variants: dict[
        tuple[tuple[str, str | None], tuple[str, ...]], set[str]
    ] = defaultdict(set)
    for entity_variants in variants_by_entity.values():
        has_explicit_failure = any(
            timing == ("label", "Puzzle test failed")
            for timing, _ in entity_variants
        )
        for key, sources in entity_variants.items():
            timing = key[0]
            is_combo_failure = (
                timing[0] == "label"
                and bool(
                    timing[1]
                    and re.fullmatch(r"If \d+ or fewer combos", timing[1])
                )
            )
            if has_explicit_failure and is_combo_failure:
                continue
            variants[key].update(sources)
    return dict(variants)


def _fold_random_into_numbered(variants):
    # a numbered move in one source and the same move in another's random set are one move
    random_key = ("label", "One at random")
    folded = {key: set(sources) for key, sources in variants.items()}
    for key in list(folded):
        if key not in folded or key[0] != random_key:
            continue
        matches = [
            other
            for other in folded
            if other[0][0] == "action" and other[1] == key[1]
        ]
        if len(matches) == 1:
            folded[key].update(folded.pop(matches[0]))
    return folded


def _fold_unspecified_amounts(variants):
    # an unspecified amount yields to a stated one at the same timing
    folded = {key: set(sources) for key, sources in variants.items()}
    for key in list(folded):
        if key not in folded:
            continue
        timing, details = key
        vague = [i for i, detail in enumerate(details) if "unspecified" in detail]
        if len(vague) != 1:
            continue
        i = vague[0]
        matches = [
            other
            for other in folded
            if other != key
            and other[0] == timing
            and len(other[1]) == len(details)
            and "unspecified" not in other[1][i]
            and all(a == b for j, (a, b) in enumerate(zip(other[1], details)) if j != i)
        ]
        if len(matches) == 1:
            folded[matches[0]].update(folded.pop(key))
    return _fold_random_into_numbered(folded)


def _prefer_source_consensus(
    variants_by_entity: dict[
        str, dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]
    ],
) -> dict[
    str, dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]]
]:
    preferred = {}
    for entity, variants in variants_by_entity.items():
        variants = _fold_unspecified_amounts(variants)
        by_timing: dict[
            tuple[str, str | None],
            list[tuple[tuple[str, str | None], tuple[str, ...]]],
        ] = defaultdict(list)
        for key in variants:
            by_timing[key[0]].append(key)

        discarded = set()
        for keys in by_timing.values():
            if len(keys) < 2:
                continue
            counts = {key: len(variants[key]) for key in keys}
            most_sources = max(counts.values())
            leaders = [key for key, count in counts.items() if count == most_sources]
            if most_sources >= 2 and len(leaders) == 1:
                discarded.update(key for key in keys if key != leaders[0])

        preferred[entity] = {
            key: sources for key, sources in variants.items() if key not in discarded
        }
    return preferred


def _board_change_timing_priority(key: tuple[str, str | None]) -> int:
    kind, value = key
    if kind == "label" and (
        value == "Preemptive"
        or bool(value and re.fullmatch(r"Below \d+% HP", value))
    ):
        return 3
    if kind == "label" and value not in {"Unknown timing", "Normal action"}:
        return 2
    if kind in {"action", "first_action", "sequence"} or (
        kind == "label" and value and value.startswith("Normal action")
    ):
        return 1
    return 0


def _is_color_detail(detail: str) -> bool:
    colors = ROULETTE_ORB_COLORS
    return detail == "All colors" or (
        bool(detail)
        and all(color in colors for color in detail.split(", "))
    )


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
        appear = primary_floor.get("appear")
        if appear is None:
            appear = next(
                (
                    floor.get("appear")
                    for floor in source_floors.values()
                    if floor.get("appear") is not None
                ),
                None,
            )
        one_of = bool(appear == 1 and len(primary_enemies) > 1)
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

        enemy_entity_by_source: dict[str, dict[int, str]] = defaultdict(dict)
        entity_names: dict[str, str] = {}
        primary_entities: set[str] = set()
        for index, enemy in enumerate(primary_enemies):
            entity = f"primary:{index}"
            primary_entities.add(entity)
            card = enemy.get("card")
            entity_names[entity] = (
                card_names.get(str(card)) if card is not None else None
            ) or enemy.get("name_jp", "Unknown enemy")
            enemy_entity_by_source[primary][id(enemy)] = entity
            for source, candidate in matched[index].items():
                enemy_entity_by_source[source][id(candidate)] = entity

        tags_by_source: dict[str, set[str]] = defaultdict(set)
        details_by_tag: dict[str, list[str]] = defaultdict(list)
        trait_details_by_tag: dict[str, list[str]] = defaultdict(list)
        entities_by_tag: dict[str, set[str]] = defaultdict(set)
        variants_by_entity_tag: dict[
            str,
            dict[
                str,
                dict[tuple[tuple[str, str | None], tuple[str, ...]], set[str]],
            ],
        ] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        for source, floor in source_floors.items():
            for enemy_index, enemy in enumerate(floor.get("enemies", [])):
                entity = enemy_entity_by_source[source].get(id(enemy))
                if entity is None:
                    entity = f"{source}:{enemy_index}"
                    card = enemy.get("card")
                    entity_names[entity] = (
                        card_names.get(str(card)) if card is not None else None
                    ) or enemy.get("name_jp", "Unknown enemy")
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
                        entities_by_tag[tag].add(entity)
                        variant_key = (when_key, tuple(details))
                        variants_by_entity_tag[tag][entity][variant_key].add(source)
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
                        entities_by_tag[tag].add(entity)
                        for detail in extract_details(trait):
                            if detail not in details_by_tag[tag]:
                                details_by_tag[tag].append(detail)
                            if detail not in trait_details_by_tag[tag]:
                                trait_details_by_tag[tag].append(detail)
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
            entity_variants = variants_by_entity_tag.get(tag, {})
            if tag == "Roulette":  # roulette paired before consensus
                entity_variants = {
                    entity: _consolidate_roulette_variants(found)
                    for entity, found in entity_variants.items()
                }
            variants_by_entity = _prefer_source_consensus(entity_variants)
            variant_entities: dict[
                tuple[tuple[str, str | None], tuple[str, ...]], set[str]
            ] = defaultdict(set)
            if tag == "Attribute absorb":
                variants = {}
                for entity, entity_variants in variants_by_entity.items():
                    entity_variants = _consolidate_preferred_variants(
                        tag, entity_variants
                    )
                    for key, variant_sources in entity_variants.items():
                        variants.setdefault(key, set()).update(variant_sources)
                        variant_entities[key].add(entity)
                show_enemy_context = one_of or len(variants_by_entity) > 1
                not_reported_for = (
                    sorted(
                        entity_names[entity]
                        for entity in primary_entities
                        - entities_by_tag.get(tag, set())
                    )
                    if one_of
                    and entities_by_tag.get(tag, set()) <= primary_entities
                    else []
                )
            else:
                variants = _prioritize_puzzle_test_failure(
                    variants_by_entity
                )
                for (when_key, variant_details), variant_sources in list(
                    variants.items()
                ):
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
                variants = _consolidate_preferred_variants(tag, variants)
                show_enemy_context = False
                not_reported_for = []
            if variants:
                details = list(
                    dict.fromkeys(
                        [
                            ", ".join(variant_details)
                            for _, variant_details in variants
                            if variant_details
                        ]
                        + trait_details_by_tag.get(tag, [])
                    )
                )
                details = [
                    detail
                    for detail in details
                    if not any(
                        other.startswith(f"{detail}, ")
                        for other in details
                        if detail.startswith("for ")
                    )
                ]
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
                            **(
                                {
                                    "enemies": sorted(
                                        {
                                            entity_names[entity]
                                            for entity in variant_entities[
                                                (when_key, variant_details)
                                            ]
                                        }
                                    )
                                }
                                if tag == "Attribute absorb" and show_enemy_context
                                else {}
                            ),
                        }
                        for (when_key, variant_details), variant_sources in sorted(
                            variants.items()
                        )
                    ],
                    **(
                        {"not_reported_for": not_reported_for}
                        if not_reported_for
                        else {}
                    ),
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
                            "already_enraged": action.get("already_enraged", False),
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
                "one_of": one_of,
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
        if order is not None:
            return "action", str(order)
    if kind == "normal":
        match = re.fullmatch(r"Normal action (\d+)", when)
        if match:
            return "action", match.group(1)
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
    if kind == "first_action":
        return "First action"
    if kind == "sequence":
        return f"Action {value}" if value else "Used in order"
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
