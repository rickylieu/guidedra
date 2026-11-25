"""Dungeon-level floor tags, summaries, and cross-source checks."""

from __future__ import annotations

import re
from statistics import median
from typing import Any

from glossary import extract_tags, normalize_text


def apply_rules(
    merged: dict[str, Any],
    records: dict[str, dict[str, Any]],
    diagnostics: dict[str, list[Any]],
) -> None:
    for source, record in records.items():
        source_tags: set[str] = set()
        for floor in record.get("floors", []):
            for enemy in floor.get("enemies", []):
                for action in enemy.get("actions", []):
                    source_tags.update(action.get("tags", []))
                for trait in enemy.get("traits_jp", []):
                    source_tags.update(extract_tags(trait))

        for must_counter in record.get("must_counter_jp", []):
            tags = extract_tags(must_counter)
            if not tags:
                diagnostics["must_counter_misses"].append(
                    {"source": source, "text_jp": must_counter, "tag": None}
                )
                continue
            for tag in tags:
                if tag not in source_tags:
                    diagnostics["must_counter_misses"].append(
                        {"source": source, "text_jp": must_counter, "tag": tag}
                    )

        for line in record.get("rules", {}).get("lines_jp", []):
            if _translate_rule(line) is None:
                diagnostics["untranslated_rules"].append(
                    {"source": source, "text_jp": line}
                )

    baseline, excluded_action_ids = _normal_hit_analysis(merged.get("floors", []))
    merged["normal_hit_baseline"] = baseline
    merged["damage_progression"] = damage_progression(
        merged.get("floors", []), baseline, excluded_action_ids
    )
    summary: dict[str, list[str]] = {}
    for floor in merged.get("floors", []):
        label = floor_label(floor)
        if "Max HP halved" in {tag["name"] for tag in floor.get("tags", [])}:
            floor["halves_max_hp"] = True
        for tag in floor.get("tags", []):
            ignored_floor_three_bind = (
                merged.get("slug") == "tenkyu-challenge"
                and floor.get("number") == 3
                and tag["name"] in {"Awoken bind", "Bind"}
            )
            if tag["critical"] and not ignored_floor_three_bind:
                summary.setdefault(tag["name"], []).append(label)
    merged["summary"] = summary

    notes = [
        translated
        for line in merged["rules"].get("lines_jp", [])
        if (translated := _translate_rule(line)) is not None
    ]
    merged["rules"]["notes"] = list(dict.fromkeys(notes))


def normal_hit_baseline(floors: list[dict[str, Any]]) -> int | None:
    """Return the median of comparable non-enraged hit actions."""
    return _normal_hit_analysis(floors)[0]


def _normal_hit_analysis(
    floors: list[dict[str, Any]],
) -> tuple[int | None, set[int]]:
    actions = [
        action
        for floor in floors
        for enemy in floor.get("enemies", [])
        for action in enemy.get("actions", [])
        if action.get("hit") is not None
        and action["hit"] > 0
        and not action.get("enraged", False)
    ]
    comparison_median = (
        median([action["hit"] for action in actions]) if actions else None
    )
    excluded_action_ids = {
        id(action)
        for action in actions
        if action.get("timing_kind") == "preemptive"
        and comparison_median is not None
        and action["hit"] < comparison_median / 4
    }
    candidates = [
        action["hit"] for action in actions if id(action) not in excluded_action_ids
    ]
    if not candidates:
        return None, excluded_action_ids

    baseline = median(candidates)
    normal_hits = [hit for hit in candidates if hit <= baseline * 4]
    while normal_hits:
        refined = median(normal_hits)
        if refined == baseline:
            break
        baseline = refined
        normal_hits = [hit for hit in candidates if hit <= baseline * 4]
    return int(median(normal_hits)) if normal_hits else None, excluded_action_ids


def hit_multiple(hit: int | None, baseline: int | None) -> float | None:
    if hit is None or baseline is None or baseline <= 0:
        return None
    return int((hit / baseline) * 2 + 0.5) / 2


def hit_severity(hit: int | None, baseline: int | None) -> str | None:
    if hit is None or baseline is None or baseline <= 0:
        return None
    if hit > 4 * baseline:
        return "execute"
    if hit >= 2 * baseline:
        return "large"
    return None


def action_hit_severity(action: dict[str, Any], baseline: int | None) -> str | None:
    hit = action.get("hit")
    if action.get("enraged"):
        if hit is None or baseline is None or baseline <= 0:
            return None
        return "large" if hit >= baseline * 2 else None
    return hit_severity(hit, baseline)


def damage_progression(
    floors: list[dict[str, Any]],
    baseline: int | None,
    excluded_action_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Group comparable floor medians and ranges; omit enraged and execute hits."""
    if excluded_action_ids is None:
        _, excluded_action_ids = _normal_hit_analysis(floors)

    ranges: list[dict[str, Any]] = []
    missing_floors: list[int] = []
    current: dict[str, Any] | None = None
    previous_range_median: int | None = None

    def finish_range() -> None:
        nonlocal current, previous_range_median
        if current is None:
            return
        included_hits = current["hits"]
        representative = int(median(included_hits))
        item: dict[str, Any] = {
            "start_floor": current["start_floor"],
            "end_floor": current["end_floor"],
            "median_hit": representative,
            "min_hit": min(included_hits),
            "max_hit": max(included_hits),
        }
        if current["start_floor"] == current["end_floor"]:
            item["label"] = f"Floor {current['start_floor']}"
        else:
            item["label"] = (
                f"Floors {current['start_floor']}–{current['end_floor']}"
            )
        if (
            previous_range_median is not None
            and representative > previous_range_median * 1.5
        ):
            item["increase_multiple"] = hit_multiple(
                representative, previous_range_median
            )
            item["increase_from_hit"] = previous_range_median
        ranges.append(item)
        previous_range_median = representative
        current = None

    numbered_floors = sorted(
        (floor for floor in floors if floor.get("number") is not None),
        key=lambda floor: floor["number"],
    )
    excluded_floors = []
    for floor in numbered_floors:
        excluded_hits = sorted(
            {
                action["hit"]
                for enemy in floor.get("enemies", [])
                for action in enemy.get("actions", [])
                if id(action) in excluded_action_ids
            }
        )
        if excluded_hits:
            excluded_floors.append(
                {
                    "label": floor_label(floor),
                    "hits": excluded_hits,
                    "reason": (
                        "Anomalously low preemptive hit before shields and team "
                        "transformations"
                    ),
                }
            )

    for floor in numbered_floors:
        recorded_hits = [
            action
            for enemy in floor.get("enemies", [])
            for action in enemy.get("actions", [])
            if action.get("hit") is not None
            and action["hit"] > 0
            and not action.get("enraged", False)
        ]
        normal_hits = _floor_normal_hit_samples(
            floor, baseline, excluded_action_ids
        )
        if not normal_hits:
            finish_range()
            if not recorded_hits or any(
                id(action) not in excluded_action_ids for action in recorded_hits
            ):
                missing_floors.append(floor["number"])
            continue

        floor_median = int(median(normal_hits))
        if current is not None:
            current_median = median(current["floor_medians"])
            if (
                floor_median > current_median * 1.5
                or floor_median < current_median / 1.5
            ):
                finish_range()
        if current is None:
            current = {
                "start_floor": floor["number"],
                "end_floor": floor["number"],
                "floor_medians": [floor_median],
                "hits": list(normal_hits),
            }
        else:
            current["end_floor"] = floor["number"]
            current["floor_medians"].append(floor_median)
            current["hits"].extend(normal_hits)
    finish_range()

    invade_hits = [
        action["hit"]
        for floor in floors
        if floor.get("number") is None
        for enemy in floor.get("enemies", [])
        for action in enemy.get("actions", [])
        if action.get("hit") is not None
        and action["hit"] > 0
        and not action.get("enraged", False)
        and id(action) not in excluded_action_ids
        and hit_severity(action["hit"], baseline) != "execute"
    ]
    return {
        "range_change_multiple": 1.5,
        "ranges": ranges,
        "missing_floors": missing_floors,
        "excluded_floors": excluded_floors,
        "invade_median_hit": int(median(invade_hits)) if invade_hits else None,
    }


def _floor_normal_hit_samples(
    floor: dict[str, Any],
    baseline: int | None,
    excluded_action_ids: set[int],
) -> list[int]:
    eligible = [
        (enemy_index, action)
        for enemy_index, enemy in enumerate(floor.get("enemies", []))
        for action in enemy.get("actions", [])
        if action.get("hit") is not None
        and action["hit"] > 0
        and not action.get("enraged", False)
        and id(action) not in excluded_action_ids
        and hit_severity(action["hit"], baseline) != "execute"
    ]
    simultaneous_appearances = (
        isinstance(floor.get("appear"), int)
        and floor["appear"] > 1
        and not floor.get("one_of", False)
    )
    if not simultaneous_appearances:
        return [action["hit"] for _, action in eligible]

    by_event: dict[tuple[Any, ...], dict[int, list[int]]] = {}
    for enemy_index, action in eligible:
        event = (
            action.get("timing_kind"),
            action.get("when"),
            action.get("order"),
        )
        by_event.setdefault(event, {}).setdefault(enemy_index, []).append(action["hit"])

    return [
        sum(int(median(enemy_hits)) for enemy_hits in enemies.values())
        for enemies in by_event.values()
    ]


def floor_label(floor: dict[str, Any]) -> str:
    if floor.get("number") is not None:
        return f"Floor {floor['number']}"
    invade = floor.get("invade_floors", [])
    if invade:
        return f"Invade (Floor {' or '.join(map(str, invade))})"
    return "Invade"


def _translate_rule(value: str) -> str | None:
    text = normalize_text(value)
    match = re.search(r"制限時間\s*(\d+)\s*分", text)
    if match:
        return f"Time limit: {match.group(1)} minutes"
    return None
