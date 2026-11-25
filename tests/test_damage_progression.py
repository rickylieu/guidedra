from rules import (
    action_hit_severity,
    damage_progression,
    hit_multiple,
    normal_hit_baseline,
)


def _floor(number, *hits):
    return {
        "number": number,
        "enemies": [
            {"actions": [{"hit": hit} for hit in hits]},
        ],
    }


def test_progression_uses_stable_medians_and_excludes_execute_only_floors():
    result = damage_progression(
        [
            _floor(1, 10, 12),
            _floor(2, 11),
            _floor(3, 1_000),
            _floor(4, 12),
            _floor(5),
            _floor(6, 25),
        ],
        baseline=20,
    )

    assert result["missing_floors"] == [3, 5]
    assert result["ranges"] == [
        {
            "start_floor": 1,
            "end_floor": 2,
            "median_hit": 11,
            "min_hit": 10,
            "max_hit": 12,
            "label": "Floors 1–2",
        },
        {
            "start_floor": 4,
            "end_floor": 4,
            "median_hit": 12,
            "min_hit": 12,
            "max_hit": 12,
            "label": "Floor 4",
        },
        {
            "start_floor": 6,
            "end_floor": 6,
            "median_hit": 25,
            "min_hit": 25,
            "max_hit": 25,
            "label": "Floor 6",
            "increase_multiple": 2.0,
            "increase_from_hit": 12,
        },
    ]


def test_hit_multiple_rounds_to_nearest_half():
    assert hit_multiple(45, 20) == 2.5
    assert hit_multiple(55, 20) == 3.0


def test_normal_hit_baseline_excludes_enraged_hits_and_uses_median():
    assert normal_hit_baseline(
        [
            _floor(1, 10, 12),
            {
                "number": 2,
                "enemies": [
                    {
                        "actions": [
                            {"hit": 1_000_000, "enraged": True},
                            {"hit": 10},
                        ]
                    }
                ],
            },
        ]
    ) == 10


def test_floor_range_pools_hits_from_every_enemy():
    result = damage_progression(
        [
            {
                "number": 6,
                "enemies": [
                    {"actions": [{"hit": 4_000_000}]},
                    {"actions": [{"hit": 8_000_000}]},
                ],
            }
        ],
        baseline=10_000_000,
    )

    assert result["ranges"] == [
        {
            "start_floor": 6,
            "end_floor": 6,
            "median_hit": 6_000_000,
            "min_hit": 4_000_000,
            "max_hit": 8_000_000,
            "label": "Floor 6",
        }
    ]


def test_simultaneous_enemy_damage_is_summed_per_event():
    result = damage_progression(
        [
            {
                "number": 6,
                "appear": 2,
                "enemies": [
                    {
                        "actions": [
                            {"hit": 3_780_000, "when": "Preemptive", "timing_kind": "preemptive"},
                            {"hit": 4_200_000, "when": "Normal action"},
                        ]
                    },
                    {
                        "actions": [
                            {"hit": 3_780_000, "when": "Preemptive", "timing_kind": "preemptive"},
                            {"hit": 4_200_000, "when": "Normal action"},
                        ]
                    },
                ],
            }
        ],
        baseline=12_502_500,
    )

    assert result["ranges"] == [
        {
            "start_floor": 6,
            "end_floor": 6,
            "median_hit": 7_980_000,
            "min_hit": 7_560_000,
            "max_hit": 8_400_000,
            "label": "Floor 6",
        }
    ]


def test_one_of_enemy_alternatives_are_not_summed():
    result = damage_progression(
        [
            {
                "number": 6,
                "appear": 2,
                "one_of": True,
                "enemies": [
                    {"actions": [{"hit": 4_000_000, "when": "Normal action"}]},
                    {"actions": [{"hit": 8_000_000, "when": "Normal action"}]},
                ],
            }
        ],
        baseline=10_000_000,
    )

    assert result["ranges"][0]["median_hit"] == 6_000_000
    assert result["ranges"][0]["min_hit"] == 4_000_000
    assert result["ranges"][0]["max_hit"] == 8_000_000


def test_anomalously_low_preemptive_hits_are_excluded_from_baseline_and_ranges():
    floors = [
        {
            "number": 1,
            "enemies": [
                {
                    "actions": [
                        {"hit": 22_500, "timing_kind": "preemptive"},
                        {"hit": 45_000, "timing_kind": "preemptive"},
                    ]
                }
            ],
        },
        _floor(2, 10_000_000, 12_000_000),
        _floor(3, 10_000_000, 11_000_000),
    ]

    assert normal_hit_baseline(floors) == 10_500_000
    result = damage_progression(floors, baseline=10_500_000)

    assert result["missing_floors"] == []
    assert result["excluded_floors"] == [
        {
            "label": "Floor 1",
            "hits": [22_500, 45_000],
            "reason": "Anomalously low preemptive hit before shields and team transformations",
        }
    ]
    assert result["ranges"] == [
        {
            "start_floor": 2,
            "end_floor": 3,
            "median_hit": 10_500_000,
            "min_hit": 10_000_000,
            "max_hit": 12_000_000,
            "label": "Floors 2–3",
        }
    ]


def test_enraged_hits_remain_large_instead_of_being_classified_as_execute():
    assert (
        action_hit_severity({"hit": 50_000_000, "enraged": True}, 10_000_000)
        == "large"
    )
    assert (
        action_hit_severity({"hit": 50_000_000, "enraged": False}, 10_000_000)
        == "execute"
    )


def test_invade_label_uses_floor_disjunction():
    from rules import floor_label

    assert floor_label({"number": None, "invade_floors": [6, 8]}) == "Invade (Floor 6 or 8)"
