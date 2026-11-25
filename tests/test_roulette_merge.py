from merge import _consolidate_roulette_variants


def test_roulette_color_subsets_merge_without_crossing_trigger_duration_or_count():
    super_resolve = ("on_super_resolve", None)
    normal_action = ("normal", None)
    variants = {
        (super_resolve, ("for 4 turns", "Heart", "2 orbs")): {"AppMedia"},
        (super_resolve, ("for 4 turns", "Water, Dark, Heart", "2 orbs")): {
            "GameWith"
        },
        (normal_action, ("for 4 turns", "Heart", "2 orbs")): {"Altema"},
        (super_resolve, ("for 5 turns", "Heart", "2 orbs")): {"Game8"},
        (super_resolve, ("for 4 turns", "Heart", "3 orbs")): {"Altema"},
    }

    assert _consolidate_roulette_variants(variants) == {
        (super_resolve, ("for 4 turns", "Water, Dark, Heart", "2 orbs")): {
            "AppMedia",
            "GameWith",
        },
        (normal_action, ("for 4 turns", "Heart", "2 orbs")): {"Altema"},
        (super_resolve, ("for 5 turns", "Heart", "2 orbs")): {"Game8"},
        (super_resolve, ("for 4 turns", "Heart", "3 orbs")): {"Altema"},
    }
