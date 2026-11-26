"""Japanese PAD dungeon text annotation and English glossary."""

from __future__ import annotations

import copy
import re
import unicodedata
from decimal import Decimal
from typing import Any


CRITICAL_TAGS = {
    "Awoken bind",
    "Unmatchable",
    "Invade",
    "Void buffs",
    "Full-board change",
    "One-shot required",
    "Max HP halved",
    "Super blind",
    "Damage void",
    "Damage absorb",
    "Attribute absorb",
    "Combo void",
    "Skill bind",
    "Void assists",
    "Skill delay",
    "Bind",
    "Roulette",
    "Damage cap set",
    "Invulnerable",
    "Sliver-HP enrage",
    "Enrage",
    "Countdown lethal",
}

ORB_NAMES = {
    "火": "Fire",
    "水": "Water",
    "木": "Wood",
    "光": "Light",
    "闇": "Dark",
    "回復": "Heart",
    "お邪魔": "Jammer",
    "爆弾": "Bomb",
    "毒": "Poison",
    "猛毒": "Mortal poison",
}
TYPE_NAMES = {
    "神": "God",
    "ドラゴン": "Dragon",
    "悪魔": "Devil",
    "マシン": "Machine",
    "バランス": "Balanced",
    "攻撃": "Attacker",
    "体力": "Physical",
    "回復": "Healer",
    "進化用": "Evo material",
    "能力覚醒用": "Awoken material",
    "強化合成用": "Enhance material",
    "売却用": "Redeemable",
}
NUMBER_UNITS = {
    "万": Decimal(10_000),
    "億": Decimal(100_000_000),
    "兆": Decimal(1_000_000_000_000),
}

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_AMOUNT = rf"{_NUMBER}(?:兆|億|万)?(?:{_NUMBER}(?:兆|億|万)?)*"
_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)(兆|億|万)?")
_CIRCLED_ORDERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_EXACT_ACTION_ANNOTATIONS = {
    "ダメージを与えられるようになる": "You can inflict damage",
    "全ドロップを入れ替える": "Refreshes board",
}
_HIT_RE = re.compile(
    rf"(?P<lower>{_AMOUNT})(?:\s*[〜～~−-]\s*(?P<upper>{_AMOUNT}))?\s*ダメージ"
)
_MULTI_HIT_RE = re.compile(r"の?連続攻撃")
_THORN_COUNT_RE = re.compile(
    r"ドロップ(?:を)?(\d+)個(?:を|が)?(?:トゲ|棘)|(?:トゲ|棘)(?:ドロップ)?(?:を)?(\d+)個"
)
_NORMAL_ORDER_RE = re.compile(r"通常(?:行動|攻撃)\s*(\d+)")
_COUNTDOWN_RE = re.compile(r"カウントダウン\s*(\d+)")


def normalize_text(text: str) -> str:
    """Apply the normalization used for Japanese guide text."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def parse_japanese_number(value: str | int | float | Decimal) -> int | None:
    """Convert Japanese 万/億/兆 amounts or comma-separated digits to an integer."""
    if isinstance(value, (int, float, Decimal)):
        return int(value)

    text = normalize_text(value).replace(",", "").replace("約", "").replace(" ", "")
    matches = list(_NUMBER_RE.finditer(text))
    if not matches:
        return None

    total = sum(
        Decimal(match.group(1)) * NUMBER_UNITS.get(match.group(2), Decimal(1))
        for match in matches
    )
    return int(total)


def format_number(value: int) -> str:
    """Format a number with a three-significant-digit K/M/B/T suffix."""
    for divisor, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if value >= divisor:
            short = f"{value / divisor:.3g}"
            return f"{short}{suffix}"
    return str(value)


_TAG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Awoken bind", re.compile(r"覚醒(?:スキル)?無効")),
    ("Unmatchable", re.compile(r"消せない(?:ドロップ)?|消去不可|消せなくなる")),
    ("Invade", re.compile(r"乱入")),
    ("Void buffs", re.compile(r"スキル効果(?:リセット|解除|打ち消し)|スキル効果を解除")),
    ("One-shot required", re.compile(r"ワンパン必須|1ターンで倒す")),
    ("Max HP halved", re.compile(r"最大HP半減|HP半減")),
    ("Super blind", re.compile(r"超暗闇")),
    ("Damage void", re.compile(r"ダメージ無効|\d+(?:\.\d+)?億以上無効")),
    ("Combo void", re.compile(r"コンボ以下無効")),
    ("Skill bind", re.compile(r"スキル封印|スキル使用不可")),
    ("Void assists", re.compile(r"アシスト無効")),
    ("Skill delay", re.compile(r"スキル遅延")),
    ("Bind", re.compile(r"バインド")),
    ("Invulnerable", re.compile(r"ダメージ(?:を|が)?与えられない|与えられなくなる")),
    ("Sliver-HP enrage", re.compile(r"ミリ残し発狂")),
    ("Damage absorb", re.compile(r"ダメージ吸収|\d+(?:\.\d+)?億以上吸収")),
    ("Attribute absorb", re.compile(r"属性吸収|ランダム1色吸収|(?:\[?(?:火|水|木|光|闇|回復)\]?)+吸収")),
    ("Combo absorb", re.compile(r"コンボ吸収|コンボ以下吸収")),
    ("Damage cap set", re.compile(r"上限値|ダメージ上限")),
    ("Status immunity", re.compile(r"状態異常無効")),
    ("Enemy shield", re.compile(r"シールド")),
    ("Board change", re.compile(r"盤面.{0,12}(?:変化|マス)|\d+[×x]\d+マス")),
    ("Move-time change", re.compile(r"操作時間")),
    ("Roulette", re.compile(r"ルーレット")),
    ("Blind", re.compile(r"(?<!超)暗闇")),
    ("Clouds", re.compile(r"雲")),
    ("Tape", re.compile(r"テープ|操作不可")),
    ("Locks", re.compile(r"ロック")),
    ("Poison", re.compile(r"毒")),
    ("Reduction required", re.compile(r"軽減必須")),
    ("Big hit / lethal", re.compile(r"大ダメージ|即死")),
    ("Enemy ATK up", re.compile(r"攻撃力(?:が)?\d+(?:\.\d+)?倍")),
    ("Reduce ATK", re.compile(r"攻撃力(?:が)?(?:激減|減少)")),
    ("Your RCV down", re.compile(r"回復力(?:が)?(?:半減|減少)")),
    ("Enemy DEF up", re.compile(r"防御力(?:が)?\d+(?:\.\d+)?(?:兆|億|万)増加")),
    ("Enemy damage reduction", re.compile(r"ダメージ(?:を)?(?:半減|激減)|受けるダメージを半減|\d+%軽減")),
    (
        "Orb change",
        re.compile(
            r"全ドロップ.{0,80}(?:変化|変換)|(?:両端|縦|最上段).{0,8}列.{0,80}(?:変化|変換)"
            r"|盤面を.{0,80}変化|ドロップリフレッシュ|全ドロップを入れ替える|回復陣|花火"
        ),
    ),
    ("Enemy attribute change", re.compile(r"自属性変更|敵の属性が.{1,16}に変化|属性変化")),
    ("No skyfall combos", re.compile(r"落ちコンなし")),
    ("Combo reduction", re.compile(r"コンボ減算|コンボ減少")),
    ("Weakened orbs", re.compile(r"弱化|弱体化")),
    (
        "Thorn orbs",
        re.compile(r"トゲ目覚め|棘目覚め|トゲドロップ目覚め|" + _THORN_COUNT_RE.pattern),
    ),
    ("Jammers", re.compile(r"(?:お邪魔|\[お邪魔\])目覚め")),
    ("Bombs", re.compile(r"爆弾")),
    ("Skill charge", re.compile(r"スキルチャージ")),
    ("Skill haste", re.compile(r"スキルヘイスト")),
    ("Enemy turn timer change", re.compile(r"行動ターンが.{1,12}変化")),
    ("Charging", re.compile(r"溜め")),
    ("Destroy orbs", re.compile(r"を破壊")),
)


def _is_enrage(text: str) -> bool:
    return bool(
        re.search(r"攻撃力(?:が)?\d+(?:\.\d+)?倍.{0,12}999ターン", text)
        or re.search(r"999ターン.{0,12}攻撃力(?:が)?\d+(?:\.\d+)?倍", text)
    )


def extract_tags(text_jp: str) -> list[str]:
    text = normalize_text(text_jp)
    tags = [name for name, pattern in _TAG_PATTERNS if pattern.search(text)]
    if "Destroy orbs" in tags and "Bombs" in tags:
        rest = re.sub(r"[\[\]火水木光闇回復お邪魔爆弾猛毒と・、]+(?:ドロップ)?を破壊", "", text)
        if "爆弾" not in rest:
            tags.remove("Bombs")

    if "超根性" in text:
        tags.append("Super resolve")
    elif "根性" in text:
        tags.append("Resolve")

    if _is_enrage(text):
        tags = [tag for tag in tags if tag != "Enemy ATK up"]
        tags.append("Enrage")
    else:
        attack = re.search(r"攻撃力(?:が)?(\d+(?:\.\d+)?)倍", text)
        if attack:
            if Decimal(attack.group(1)) < 1:
                tags = [tag for tag in tags if tag != "Enemy ATK up"]
                tags.append("Reduce ATK")
            elif "Enemy ATK up" not in tags:
                tags.append("Enemy ATK up")

    if re.search(
        r"(?:火|水|木|光|闇|回復|お邪魔|爆弾|猛毒|毒)ドロップ目覚め"
        r"|(?:火|水|木|光|闇|回復|猛毒|毒)目覚め",
        text,
    ):
        tags.append("Skyfall increase")
    if re.search(r"(?:\[(?:火|水|木|光|闇|回復|猛毒|毒)\])+(?:ドロップ)?目覚め", text):
        tags.append("Skyfall increase")
    if re.search(
        r"(?:\[(?:火|水|木|光|闇|回復|お邪魔|爆弾|猛毒|毒)\]|"
        r"(?:火|水|木|光|闇|回復|お邪魔|爆弾|猛毒|毒)(?:ドロップ)?)を?\d+個(?:ずつ)?生成",
        text,
    ):
        tags.append("Orbs spawned")
        tags = [tag for tag in tags if tag != "Poison"]
    if "Skyfall increase" in tags or "Roulette" in tags:
        tags = [tag for tag in tags if tag != "Poison"]
    if "先制" in text:
        tags.append("Preemptive")
    if _is_full_board_change(text):
        tags.append("Full-board change")

    return list(dict.fromkeys(tags))


def is_critical(tag: str) -> bool:
    return tag in CRITICAL_TAGS


def parse_timing(timing_jp: str, order: int | str | None = None) -> dict[str, str]:
    text = normalize_text(timing_jp)
    if text and re.search(r"順番に.*使用", text):
        label = "Repeats in order" if "繰り返し" in text else "Used in order"
        return {"kind": "sequence", "label": label}
    if not text or "先制" in text:
        return {"kind": "preemptive", "label": "Preemptive"}

    countdown = _COUNTDOWN_RE.search(text)
    if countdown:
        # annotate_record turns these into turns once it has seen the whole enemy.
        return {"kind": "countdown", "label": f"Countdown {countdown.group(1)}"}

    if "全部位破壊時" in text:
        return {"kind": "all_parts_break", "label": "When all parts break"}
    if "部位破壊時" in text:
        return {"kind": "part_break", "label": "When a part breaks"}
    if "超根性発動時" in text or text == "超根性":
        return {"kind": "on_super_resolve", "label": "On super resolve"}
    if "死亡時" in text:
        return {"kind": "on_death", "label": "On death"}
    if "パズル教室クリア後" in text:
        return {"kind": "after_lesson", "label": "After the puzzle test"}
    if "成功時" in text:
        return {"kind": "lesson_pass", "label": "Puzzle test passed"}
    if "失敗時" in text:
        return {"kind": "lesson_fail", "label": "Puzzle test failed"}
    if "ランダムに使用" in text:
        return {"kind": "random", "label": "One at random"}

    match = re.search(r"(\d+)\s*コンボ以上時", text)
    if match:
        return {"kind": "combo_ge", "label": f"If {match.group(1)}+ combos"}
    match = re.search(r"(\d+)\s*コンボ以下時", text)
    if match:
        return {"kind": "combo_le", "label": f"If {match.group(1)} or fewer combos"}
    match = re.search(r"残り(\d+)体以下になると", text)
    if match:
        return {"kind": "remaining_le", "label": f"When {match.group(1)} or fewer remain"}
    match = re.search(r"残り(\d+)体(?:になると|時)", text)
    if match:
        return {"kind": "remaining_eq", "label": f"When {match.group(1)} remains"}
    match = re.search(r"HP\s*(\d+)%以下(?:時)?", text)
    if match:
        return {"kind": "hp_below", "label": f"Below {match.group(1)}% HP"}
    match = re.search(r"(\d+)回目行動時", text)
    if match:
        return {"kind": "nth_action", "label": f"Action {match.group(1)}"}
    if "初回行動" in text:
        return {"kind": "first_action", "label": "First action"}
    match = re.search(r"(\d+)ターン毎", text)
    if match:
        return {"kind": "every_n_turns", "label": f"Every {match.group(1)} turns"}
    if "毎ターン" in text:
        return {"kind": "every_turn", "label": "Every turn"}
    match = re.search(r"(\d+)ターン目", text)
    if match:
        return {"kind": "turn", "label": f"Turn {match.group(1)}"}
    if "通常行動" in text or "通常攻撃" in text:
        ordinal = _timing_order(timing_jp)
        if ordinal is None:
            ordinal = _parse_order(order)
        return {
            "kind": "normal",
            "label": f"Normal action {ordinal}" if ordinal is not None else "Normal action",
        }
    return {"kind": "unknown", "label": "Unknown timing"}


def _parse_order(order: int | str | None) -> int | None:
    if order is None:
        return None
    if isinstance(order, int):
        return order
    match = re.search(r"\d+", normalize_text(order))
    return int(match.group()) if match else None


def _timing_order(timing_jp: str) -> int | None:
    """Read the action number written in a timing header, e.g. 通常行動①."""
    for character in timing_jp:
        if character in _CIRCLED_ORDERS:
            return _CIRCLED_ORDERS.index(character) + 1
    match = _NORMAL_ORDER_RE.search(normalize_text(timing_jp))
    return int(match.group(1)) if match else None


def extract_details(text_jp: str, order: int | str | None = None) -> list[str]:
    order_number = _parse_order(order)
    marker = re.match(r"\s*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])", text_jp)
    if marker and (
        order_number is None
        or _CIRCLED_ORDERS.index(marker.group(1)) + 1 == order_number
    ):
        text_jp = text_jp[marker.end() :]
    text = normalize_text(text_jp)
    details: list[str] = []

    for match in re.finditer(r"(\d+)ターン(?!目|毎)(?:の間)?", text):
        if match.group(1) != "999":
            unit = "turn" if match.group(1) == "1" else "turns"
            details.append(f"for {match.group(1)} {unit}")

    threshold = re.search(
        r"(\d+(?:\.\d+)?(?:億|万))以上(?=(?:ダメージ)?(?:無効|吸収))",
        text,
    )
    if threshold:
        amount = parse_japanese_number(threshold.group(1))
        if amount is not None:
            details.append(f"{format_number(amount)} or more")

    match = re.search(r"(\d+)\s*コンボ以下", text)
    if match:
        details.append(f"{match.group(1)} or fewer combos")

    defense = re.search(r"防御力(?:が)?\s*(\d+(?:\.\d+)?億)増加", text)
    if defense:
        amount = parse_japanese_number(defense.group(1))
        if amount is not None:
            details.append(f"DEF +{format_number(amount)}")

    if "操作時間" in text:
        seconds = re.search(r"操作時間[^0-9]{0,8}(\d+(?:\.\d+)?)秒", text)
        multiplier = re.search(r"操作時間[^0-9]{0,8}(\d+(?:\.\d+)?)倍", text)
        reduction = re.search(r"操作時間[^0-9]{0,8}(\d+(?:\.\d+)?)%", text)
        if seconds:
            n = seconds.group(1)
            suffix = text[seconds.end() : seconds.end() + 8]
            if re.match(r"(?:減少|短縮)", suffix):
                details.append(f"reduced by {n} seconds")
            else:
                details.append(f"set to {n} seconds")
        elif multiplier:
            details.append(f"×{multiplier.group(1)}")
        elif reduction:
            details.append(f"reduced by {reduction.group(1)}%")
        elif "半減" in text:
            details.append("reduced by 50%")
        elif "激減" in text:
            details.append("greatly reduced (percentage unspecified)")
        elif re.search(r"操作時間.{0,12}(?:減少|短縮)", text):
            details.append("reduced (amount unspecified)")
    else:
        percent = re.search(r"(\d+)%軽減", text)
        if percent:
            details.append(f"{percent.group(1)}%")
        elif "半減" in text:
            details.append("50%")

    attack_multiplier = re.search(r"攻撃力(?:が)?(\d+(?:\.\d+)?)倍", text)
    attack_down_multiplier = re.search(
        r"攻撃力.{0,20}?(?:激減|減少|低下).{0,8}?\(?(\d+(?:\.\d+)?)倍",
        text,
    )
    attack_down_percent = re.search(
        r"攻撃力.{0,20}?(?:激減|減少|低下).{0,8}?\(?(\d+(?:\.\d+)?)%",
        text,
    )
    reduced_multiplier = next(
        (
            Decimal(found.group(1))
            for found in (attack_multiplier, attack_down_multiplier)
            if found and Decimal(found.group(1)) < 1
        ),
        None,
    )
    if reduced_multiplier is not None:
        amount = (Decimal(1) - reduced_multiplier) * 100
        details.append(f"ATK reduced by {format(amount.normalize(), 'f')}%")
    elif attack_down_percent:
        details.append(f"ATK reduced by {attack_down_percent.group(1)}%")
    elif "攻撃力" in text and re.search(r"激減|減少|低下", text):
        details.append("ATK greatly reduced (percentage unspecified)")
    elif attack_multiplier:
        details.append(f"×{attack_multiplier.group(1)}")

    colors = _orb_names_in(text)
    if colors:
        details.append(", ".join(colors))
    elif "ルーレット" in text:
        details.append("All colors")

    board = re.search(r"(\d+)\s*[×x]\s*(\d+)", text)
    if board:
        details.append(f"{board.group(1)}×{board.group(2)}")

    count = re.search(r"(\d+)個(ずつ)?生成", text)
    if count and "ルーレット" not in text:
        unit = "orbs each" if count.group(2) else "orbs"
        details.append(f"{count.group(1)} {unit}")
    thorns = _THORN_COUNT_RE.search(text)
    if thorns:
        details.append(f"{thorns.group(1) or thorns.group(2)} orbs")
    if "ルーレット" in text:
        positions = re.search(r"ルーレット(?:を)?\s*(\d+)\s*個", text)
        if not positions:
            positions = re.search(r"(\d+)\s*マス(?=.{0,20}ルーレット)", text)
        if positions:
            details.append(f"{positions.group(1)} orbs")
        if "最下段" in text:
            details.append("Bottom row")

    cap = re.search(
        rf"(?:上限値|ダメージ上限)(?:が|は|[:：]|\s)*({_NUMBER}(?:兆|億|万)?)",
        text,
    )
    if cap:
        amount = parse_japanese_number(cap.group(1))
        if amount is not None:
            details.append(f"cap {format_number(amount)}")

    if "スキルヘイスト" in text:
        haste = re.search(r"スキルヘイスト[^0-9]{0,16}(\d+)ターン", text)
        if haste:
            count = haste.group(1)
            duration = f"for {count} turns"
            details = [detail for detail in details if detail != duration]
            details.append(f"+{count} turn" if count == "1" else f"+{count} turns")

    shield = re.search(
        r"シールド(?:\s*[（(][^）)]*[）)])?(?:を)?\s*(\d+)\s*(?:枚|個|つ)",
        text,
    )
    if shield:
        count = int(shield.group(1))
        details.append(f"{count} shield" if count == 1 else f"{count} shields")

    if "根性" in text:
        threshold = re.search(r"(?:超根性|根性)\s*[:：]?\s*(\d+)%", text)
        details.append(f"{threshold.group(1) if threshold else '50'}%")

    return list(dict.fromkeys(details))


def _add_orb_names(fragment: str, names: list[str]) -> None:
    """Add the orbs named in a fragment. 猛毒 never also counts as 毒."""
    has_mortal_poison = "猛毒" in fragment
    rest = fragment.replace("猛毒", "")
    for orb, name in ORB_NAMES.items():
        present = has_mortal_poison if orb == "猛毒" else orb in rest
        if present and name not in names:
            names.append(name)


def _orb_names_in(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"\[([火水木光闇回復お邪魔爆弾猛毒]+)\]", text):
        _add_orb_names(match.group(1), names)

    board_target = re.search(
        r"(?:盤面を|全ドロップ(?:を)?)(?P<target>.*?)(?:変化|変換|にする|に変える)",
        text,
    )
    target_text = board_target.group("target") if board_target else ""
    for match in re.finditer(r"([火水木光闇回復お邪魔爆弾]+)(?:陣|花火)", text):
        target_text += match.group(1)
    for match in re.finditer(r"([火水木光闇回復お邪魔爆弾]+)ルーレット", text):
        target_text += match.group(1)
    for match in re.finditer(r"([火水木光闇回復お邪魔爆弾猛毒と・、]+)(?:ドロップ)?を破壊", text):
        target_text += match.group(1)
    if target_text:
        _add_orb_names(target_text, names)
    return names


def _is_full_board_change(text: str) -> bool:
    has_full_board_phrase = bool(
        "全ドロップ" in text
        or re.search(r"盤面を.{0,40}(?:変化|変換|にする|に変える)", text)
        or re.search(r"[火水木光闇回復お邪魔爆弾]+(?:陣|花火)", text)
    )
    colors = _orb_names_in(text)
    return has_full_board_phrase and 1 <= len(colors) <= 2


def extract_hit(text_jp: str) -> tuple[int | None, list[str]]:
    text_jp = re.sub(rf"^\s*[{_CIRCLED_ORDERS}]\s*", "", text_jp)
    text = normalize_text(text_jp)
    match = _HIT_RE.search(text)
    if not match:
        return None, []

    amount = parse_japanese_number(match.group("upper") or match.group("lower"))
    if amount is None:
        return None, []

    details: list[str] = []
    multiplier_detail = re.match(r"\s*[×x]\s*(\d+)", text[match.end() :])
    if multiplier_detail:
        amount *= int(multiplier_detail.group(1))

    # (○倍時): the hit already includes the multiplier; flagged as already_enraged
    return amount, details


def _compose_text(tags: list[str], details: list[str]) -> str:
    labels = list(tags)
    remaining = list(details)
    if "Thorn orbs" in labels:
        count = next((d for d in remaining if re.fullmatch(r"\d+ orbs", d or "")), None)
        if count:
            remaining.remove(count)
            labels[labels.index("Thorn orbs")] = f"Create {count.split()[0]} thorn orbs"
    if "Destroy orbs" in labels:
        orb_words = {name.lower() for name in ORB_NAMES.values()}
        colors = next(
            (d for d in remaining if d and all(part.lower() in orb_words for part in d.split(", "))),
            None,
        )
        if colors:
            remaining.remove(colors)
            names = [part.lower() for part in colors.split(", ")]
            if len(names) > 2:
                joined = f"{', '.join(names[:-1])}, and {names[-1]}"
            else:
                joined = " and ".join(names)
            labels[labels.index("Destroy orbs")] = f"Destroy {joined} orbs"
    if "Damage cap set" in labels:
        cap = next((detail for detail in remaining if detail.startswith("cap ")), None)
        if cap:
            labels[labels.index("Damage cap set")] = f"Damage cap set to {cap[4:]}"
            remaining.remove(cap)
    if "Skill haste" in labels:
        haste = next(
            (detail for detail in remaining if re.fullmatch(r"\+\d+ turns?", detail)),
            None,
        )
        if haste:
            labels[labels.index("Skill haste")] = f"Skill haste {haste}"
            remaining.remove(haste)
    if "Enemy shield" in labels:
        shield = next(
            (detail for detail in remaining if re.fullmatch(r"\d+ shields?", detail)),
            None,
        )
        if shield:
            labels[labels.index("Enemy shield")] = f"Generate {shield}"
            remaining.remove(shield)
    line = ", ".join(labels)
    if remaining:
        sep = " - "
        line += f" ({sep.join(remaining)})"
    return line


def _is_pure_damage(text_jp: str) -> bool:
    text = normalize_text(text_jp)
    text = re.sub(rf"^[{_CIRCLED_ORDERS}]\s*", "", text)
    match = _HIT_RE.search(text)
    if not match:
        return False
    text = text[: match.start()] + text[match.end() :]
    text = re.sub(r"[（(]\s*\d+(?:\.\d+)?倍時\s*[）)]", "", text)
    text = _MULTI_HIT_RE.sub("", text)
    text = re.sub(r"[\s、,。・:：+!！?？()（）]", "", text)
    return not text


def annotate_action(action: dict[str, Any]) -> dict[str, Any]:
    annotated = copy.deepcopy(action)
    text_jp = str(annotated.get("text_jp", ""))
    tags = extract_tags(text_jp)
    timing = parse_timing(str(annotated.get("timing_jp", "")), annotated.get("order"))
    hit, hit_details = extract_hit(text_jp)
    details = list(
        dict.fromkeys(
            [*extract_details(text_jp, annotated.get("order")), *hit_details]
        )
    )
    if timing["kind"] == "preemptive" and "Preemptive" not in tags:
        tags.append("Preemptive")

    annotated.update(
        {
            "tags": tags,
            "timing_kind": timing["kind"],
            "when": timing["label"],
            "hit": hit,
            "details": details,
            "enraged": any(detail.startswith("at ×") for detail in details),
            "text": _compose_text(tags, details),
        }
    )
    if hit is not None and not (set(tags) - {"Preemptive"}) and _is_pure_damage(text_jp):
        annotated["text"] = (
            "Multi-hit attack"
            if _MULTI_HIT_RE.search(normalize_text(text_jp))
            else "Normal attack"
        )
    exact_annotation = _EXACT_ACTION_ANNOTATIONS.get(normalize_text(text_jp))
    if exact_annotation:
        annotated["text"] = exact_annotation
    return annotated


def annotate_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a source record with action annotations added."""
    annotated = copy.deepcopy(record)
    for floor in annotated.get("floors", []):
        for enemy in floor.get("enemies", []):
            enemy["traits"] = [
                english_trait(trait) for trait in enemy.get("traits_jp", [])
            ]
            enemy["traits"] = [trait for trait in enemy["traits"] if trait is not None]
            for action in enemy.get("actions", []):
                action.update(annotate_action(action))
            _number_countdown_turns(enemy.get("actions", []))
            _mark_enraged_hits(enemy.get("actions", []))
    return annotated


def _number_countdown_turns(actions: list[dict[str, Any]]) -> None:
    """Turn countdown headers into turns: the highest count is Turn 1."""
    counts: dict[int, int] = {}
    for index, action in enumerate(actions):
        if action.get("timing_kind") != "countdown":
            continue
        match = _COUNTDOWN_RE.search(normalize_text(str(action.get("timing_jp", ""))))
        if match:
            counts[index] = int(match.group(1))
    if not counts:
        return
    highest = max(counts.values())
    for index, count in counts.items():
        actions[index]["timing_kind"] = "turn"
        actions[index]["when"] = f"Turn {highest - count + 1}"


def _mark_enraged_hits(actions: list[dict[str, Any]]) -> None:
    has_one_turn_preemptive_attack_up = any(
        action.get("timing_kind") == "preemptive"
        and "Enemy ATK up" in action.get("tags", [])
        and "for 1 turn" in action.get("details", [])
        for action in actions
    )
    for action in actions:
        if action.get("hit") is None:
            continue
        action["enraged"] = bool(
            action.get("enraged")
            or (
                has_one_turn_preemptive_attack_up
                and action.get("timing_kind") == "first_action"
            )
        )


def english_trait(trait_jp: str) -> str | None:
    text = normalize_text(trait_jp)
    if "超根性" in text:
        match = re.search(
            r"(?:HP\s*|超根性\s*[:：]\s*)(\d+|？|\?)(%|兆|億|万)?",
            text,
        )
        if not match:
            return "Super resolve at 50%"
        value = match.group(1).replace("？", "?")
        if value == "?":
            value = "50"
        unit = match.group(2)
        if unit == "%":
            return f"Super resolve at {value}%"
        if unit in NUMBER_UNITS:
            amount = parse_japanese_number(f"{value}{unit}")
            if amount is not None:
                return f"Super resolve at {format_number(amount)} HP"
        return "Super resolve at ?%"
    if "根性" in text:
        match = re.search(r"(?:超根性|根性)\s*[:：]?\s*(\d+)%", text)
        return f"Resolve at {match.group(1) if match else '50'}%"
    if "半減" in text:
        types = [
            TYPE_NAMES[name]
            for name in re.findall(r"([^\s\[\]【】]+?)タイプ", text)
            if name in TYPE_NAMES
        ]
        if not types:
            return "Takes half damage from certain types"
        if len(types) == 1:
            return f"Takes half damage from {types[0]} types"
        return f"Takes half damage from {', '.join(types[:-1])} and {types[-1]} types"
    match = re.search(r"(\d+)ターン行動", text)
    if match:
        return f"Acts every {match.group(1)} turns"
    return None

# already enraged flag
_annotate_action_base = annotate_action


def annotate_action(action, *args, **kwargs):
    result = _annotate_action_base(action, *args, **kwargs)
    target = result if isinstance(result, dict) else action
    text = unicodedata.normalize("NFKC", action.get("text_jp") or "")
    if target.get("hit") and re.search(r"\(\s*\d+(?:\.\d+)?倍時\s*\)", text):
        target["already_enraged"] = True
    return result
