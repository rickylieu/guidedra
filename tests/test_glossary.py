from glossary import (
    annotate_action,
    annotate_record,
    extract_details,
    extract_hit,
    extract_tags,
    parse_japanese_number,
    parse_timing,
)


def test_japanese_number_units_are_combined():
    assert parse_japanese_number("2億5000万") == 250_000_000


def test_attack_multiplier_direction_and_enrage():
    assert extract_tags("攻撃力0.2倍") == ["Your ATK down"]
    assert extract_tags("攻撃力が10倍") == ["Enemy ATK up"]
    assert extract_tags("攻撃力が10倍：999ターン") == ["Enrage"]


def test_invulnerable_phrase_is_tagged():
    assert extract_tags("ダメージが与えられない") == ["Invulnerable"]


def test_exact_action_annotations_cover_damage_enable_and_board_refresh():
    inflict_damage = annotate_action(
        {"timing_jp": "通常行動", "text_jp": "ダメージを与えられるようになる"}
    )
    refresh_board = annotate_action(
        {"timing_jp": "通常行動", "text_jp": "全ドロップを入れ替える"}
    )

    assert inflict_damage["text"] == "You can inflict damage"
    assert refresh_board["text"] == "Refreshes board"
    assert refresh_board["tags"] == ["Orb change"]


def test_buff_void_phrasing_is_normalized():
    for text in ("スキル効果リセット", "スキル効果解除", "スキル効果打ち消し"):
        assert extract_tags(text) == ["Void buffs"]


def test_all_parts_break_timing():
    assert parse_timing("全部位破壊時") == {
        "kind": "all_parts_break",
        "label": "When all parts break",
    }


def test_puzzle_test_timing_labels():
    assert parse_timing("パズル教室クリア後")["label"] == "After the puzzle test"
    assert parse_timing("成功時")["label"] == "Puzzle test passed"
    assert parse_timing("失敗時")["label"] == "Puzzle test failed"


def test_damage_void_threshold_and_hit_extraction():
    text = "50億以上無効"
    assert extract_tags(text) == ["Damage void"]
    assert extract_details(text) == ["5B or more"]
    assert extract_details("50億以上ダメージ無効") == ["5B or more"]
    assert extract_hit("7,650,000ダメージ") == (7_650_000, [])
    assert extract_hit("①7,000,000ダメージ [闇]を9個生成") == (7_000_000, [])
    assert extract_hit("②7,140,000ダメージ") == (7_140_000, [])


def test_orb_skyfall_and_spawn_tags():
    assert "Skyfall change" in extract_tags("[光][回復]目覚め：10ターン")
    assert {"Bombs", "Orbs spawned"} <= set(extract_tags("[爆弾]を8個生成"))
    assert "8 orbs" in extract_details("[爆弾]を8個生成")


def test_colored_full_board_change_phrasing():
    for text, colors in (
        ("盤面を[光]に変化", {"Light"}),
        ("全ドロップを[回復]に変化", {"Heart"}),
        ("水回復陣", {"Water", "Heart"}),
        ("光花火", {"Light"}),
    ):
        assert "Full-board change" in extract_tags(text)
        details = " ".join(extract_details(text))
        assert all(color in details for color in colors)
    assert "Full-board change" not in extract_tags("全ドロップ変化")
    assert "Full-board change" not in extract_tags("盤面を[光][闇][回復]に変化")


def test_duration_details_preserve_turn_counts():
    assert extract_details("LF5ターンスキル遅延") == ["for 5 turns"]
    assert extract_details("覚醒無効:1ターン") == ["for 1 turn"]
    assert extract_details(
        "②50億以上ダメージ吸収:1ターン 17,820,000ダメージ", order=2
    ) == ["for 1 turn", "5B or more"]
    action = annotate_action(
        {
            "timing_jp": "",
            "text_jp": "⑤12コンボ以下無効:1ターン",
            "order": 5,
        }
    )
    assert "12 or fewer combos" in action["details"]
    assert "512 or fewer combos" not in action["details"]


def test_action_annotation_preserves_hit_multiplier_detail():
    action = {
        "timing_jp": "",
        "text_jp": "7,650,000ダメージ（5倍時）",
        "order": None,
    }
    annotated = annotate_action(action)
    assert annotated["hit"] == 7_650_000
    assert annotated["details"] == ["at ×5 ATK"]
    assert action == {
        "timing_jp": "",
        "text_jp": "7,650,000ダメージ（5倍時）",
        "order": None,
    }


def test_hit_at_an_enrage_trigger_is_not_marked_as_already_enraged():
    record = annotate_record(
        {
            "floors": [
                {
                    "enemies": [
                        {
                            "actions": [
                                {
                                    "timing_jp": "部位破壊時",
                                    "text_jp": "7,984,050ダメージ",
                                },
                                {
                                    "timing_jp": "部位破壊時",
                                    "text_jp": "攻撃力が1.3倍：999ターン",
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    )

    hit, enrage = record["floors"][0]["enemies"][0]["actions"]
    assert hit["hit"] == 7_984_050
    assert not hit["enraged"]
    assert "Enrage" in enrage["tags"]


def test_effect_details_include_requested_numeric_values():
    assert "DEF +5B" in extract_details("防御力50億増加(2ターン)")
    assert extract_details("指定4マスにルーレット生成(1ターン)") == [
        "for 1 turn",
        "All colors",
        "4 orbs",
    ]
    assert extract_details("水闇回復ルーレットを2個生成(4ターン)") == [
        "for 4 turns",
        "Water, Dark, Heart",
        "2 orbs",
    ]
    assert "Bottom row" in extract_details("最下段横1列にルーレットを生成(4ターン)")
    assert "×3" in extract_details("操作時間3倍(1ターン)")
    assert "set to 5 seconds" in extract_details("操作時間を5秒に固定")
    assert "reduced by 50%" in extract_details("操作時間半減(2ターン)")
    assert "greatly reduced (percentage unspecified)" in extract_details(
        "操作時間激減"
    )
    assert "ATK reduced by 80%" in extract_details("攻撃力0.2倍(2ターン)")
    assert "ATK reduced by 75%" in extract_details("攻撃力激減(75%)")
    assert "ATK greatly reduced (percentage unspecified)" in extract_details(
        "攻撃力激減"
    )
    assert "1 shield" in extract_details("シールド1枚生成(HP2600億)")
    assert "1 shield" in extract_details("シールドを1つ生成")
    assert "2 shields" in extract_details("シールド2枚生成")


def test_enemy_shield_count_is_composed_into_action_text():
    action = annotate_action(
        {"timing_jp": "通常行動", "text_jp": "シールドを1つ生成"}
    )
    assert action["text"] == "Generate 1 shield"
    assert action["details"] == ["1 shield"]


def test_effect_text_uses_damage_cap_and_skill_haste_values():
    cap = annotate_action(
        {"timing_jp": "通常行動", "text_jp": "全員のダメージ上限値が20億(2ターン)"}
    )
    haste = annotate_action(
        {"timing_jp": "通常行動", "text_jp": "サブスキルヘイスト(2ターン)"}
    )
    assert cap["text"] == "Damage cap set to 2B (for 2 turns)"
    assert haste["text"] == "Skill haste +2 turns"

    move_time = annotate_action(
        {"timing_jp": "通常行動", "text_jp": "操作時間半減(2ターン)"}
    )
    assert move_time["text"] == "Move-time change (for 2 turns, reduced by 50%)"


def test_pure_damage_gets_english_label_and_resolve_defaults_to_half():
    action = annotate_action(
        {"timing_jp": "", "text_jp": "8,585,000ダメージ"}
    )
    assert action["text"] == "Normal attack"
    assert action["hit"] == 8_585_000
    assert extract_details("根性") == ["50%"]
    assert extract_details("超根性:40%") == ["40%"]
