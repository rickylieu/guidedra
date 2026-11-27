from merge import (
    _consolidate_preferred_variants,
    _prioritize_puzzle_test_failure,
    _prefer_source_consensus,
    _semantic_timing,
    _semantic_timing_label,
    merge_dungeon,
)


def test_board_change_prefers_hp_trigger_over_action_number():
    variants = {
        (("action", "2"), ("Fire, Light",)): {"GameWith"},
        (("label", "Below 50% HP"), ("Fire, Light",)): {"AppMedia"},
    }

    preferred = {
        (("label", "Below 50% HP"), ("Fire, Light",)): {"AppMedia"}
    }
    for tag in ("Board change", "Full-board change", "Orb change"):
        assert _consolidate_preferred_variants(tag, variants) == preferred


def test_board_change_keeps_variants_with_different_orb_changes():
    variants = {
        (("action", "2"), ("Fire, Light",)): {"GameWith"},
        (("label", "Below 50% HP"), ("Water, Heart",)): {"AppMedia"},
    }

    assert _consolidate_preferred_variants("Full-board change", variants) == variants


def test_colored_unmatchable_and_attribute_absorb_prefer_specific_details():
    for tag in ("Unmatchable", "Attribute absorb"):
        variants = {
            (("label", "Preemptive"), ("for 1 turn",)): {"Altema"},
            (("label", "Preemptive"), ("for 1 turn", "Light, Dark")): {
                "AppMedia",
                "GameWith",
            },
        }

        assert _consolidate_preferred_variants(tag, variants) == {
            (("label", "Preemptive"), ("for 1 turn", "Light, Dark")): {
                "AppMedia",
                "GameWith",
            }
        }


def test_color_preference_does_not_merge_different_durations():
    variants = {
        (("label", "Preemptive"), ("for 1 turn",)): {"Altema"},
        (("label", "Preemptive"), ("for 2 turns", "Heart")): {"AppMedia"},
    }

    assert _consolidate_preferred_variants("Unmatchable", variants) == variants


def test_color_preference_keeps_ambiguous_specific_variants():
    variants = {
        (("label", "Preemptive"), ("for 4 turns",)): {"Altema"},
        (("label", "Preemptive"), ("for 4 turns", "Fire, Light")): {"AppMedia"},
        (("label", "Preemptive"), ("for 4 turns", "Water, Wood")): {"GameWith"},
    }

    assert _consolidate_preferred_variants("Attribute absorb", variants) == variants


def test_normal_action_number_merges_first_but_not_in_order_actions():
    normal_action = _semantic_timing(
        {"timing_kind": "normal", "when": "Normal action 1"},
        has_puzzle_test=False,
        action_interval=1,
    )
    numbered_action = _semantic_timing(
        {"timing_kind": "nth_action", "when": "Action 1"},
        has_puzzle_test=False,
        action_interval=1,
    )
    first_action = _semantic_timing(
        {"timing_kind": "first_action", "when": "First action"},
        has_puzzle_test=False,
        action_interval=1,
    )
    ordered_action = _semantic_timing(
        {"timing_kind": "sequence", "when": "Used in order", "order": 1},
        has_puzzle_test=False,
        action_interval=1,
    )

    assert normal_action == numbered_action == ("action", "1")
    assert first_action == ("action", "1")
    assert ordered_action == ("action", "1")
    assert _semantic_timing_label(first_action) == "Action 1"
    assert _semantic_timing_label(ordered_action) == "Action 1"


def test_puzzle_failure_replaces_combo_threshold_for_same_enemy_only():
    variants_by_enemy = {
        "puzzle enemy": {
            (("label", "If 11 or fewer combos"), ()): {"Altema"},
            (("label", "Puzzle test failed"), ()): {"GameWith"},
        },
        "other enemy": {
            (("label", "If 12 or fewer combos"), ()): {"AppMedia"},
        },
    }

    assert _prioritize_puzzle_test_failure(variants_by_enemy) == {
        (("label", "Puzzle test failed"), ()): {"GameWith"},
        (("label", "If 12 or fewer combos"), ()): {"AppMedia"},
    }


def test_source_consensus_selects_unique_leader_and_keeps_ties():
    variants_by_enemy = {
        "majority": {
            (("label", "Preemptive"), ("for 1 turn",)): {"AppMedia", "Game8"},
            (("label", "Preemptive"), ("for 2 turns",)): {"Altema"},
        },
        "tie": {
            (("label", "Preemptive"), ("for 1 turn",)): {"AppMedia"},
            (("label", "Preemptive"), ("for 2 turns",)): {"Altema"},
        },
        "additive": {
            (("action", "3"), ("for 1 turn",)): {"AppMedia"},
            (("action", "6"), ("for 1 turn",)): {"AppMedia"},
        },
    }

    assert _prefer_source_consensus(variants_by_enemy) == {
        "majority": {
            (("label", "Preemptive"), ("for 1 turn",)): {"AppMedia", "Game8"}
        },
        "tie": variants_by_enemy["tie"],
        "additive": variants_by_enemy["additive"],
    }


def test_floor_variants_keep_enemy_context_for_alternative_spawns():
    def enemy(card, name, action_texts=()):
        return {
            "card": card,
            "name_jp": name,
            "actions": [
                {
                    "text_jp": text,
                    "timing_jp": "先制",
                    "order": 1,
                }
                for text in action_texts
            ],
        }

    def record(enemies):
        return {"floors": [{"number": 12, "appear": 1, "enemies": enemies}]}

    records = {
        "gamewith": record(
            [
                enemy(1, "ウルド", ("[火][光]属性吸収4ターン",)),
                enemy(2, "スクルド"),
                enemy(3, "ヴェルダンディ", ("[水][木]属性吸収4ターン",)),
            ]
        ),
        "appmedia": record(
            [
                enemy(1, "ウルド", ("[火][光]属性吸収4ターン",)),
                enemy(2, "スクルド"),
                enemy(3, "ヴェルダンディ", ("[水][木]属性吸収4ターン",)),
            ]
        ),
        "altema": record(
            [
                enemy(1, "ウルド", ("属性吸収4ターン",)),
                enemy(2, "スクルド"),
                enemy(3, "ヴェルダンディ", ("属性吸収10ターン",)),
            ]
        ),
        "game8": record(
            [
                enemy(1, "ウルド", ("属性吸収4ターン",)),
                enemy(2, "スクルド"),
                enemy(3, "ヴェルダンディ", ("属性吸収4ターン",)),
            ]
        ),
    }

    merged, _ = merge_dungeon(
        {
            "slug": "test",
            "name_en": "Test",
            "name_jp": "テスト",
            "primary": "gamewith",
        },
        records,
        {},
    )
    floor = merged["floors"][0]
    absorb = next(tag for tag in floor["tags"] if tag["name"] == "Attribute absorb")

    assert floor["one_of"] is True
    assert len(floor["enemies"]) == 3
    assert absorb["not_reported_for"] == ["スクルド"]
    assert {
        (tuple(variant["details"]), tuple(variant["enemies"]))
        for variant in absorb["variants"]
    } == {
        (("for 4 turns", "Fire, Light"), ("ウルド",)),
        (("for 4 turns", "Water, Wood"), ("ヴェルダンディ",)),
    }
