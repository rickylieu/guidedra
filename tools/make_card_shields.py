"""One-off: write site/data/card_shields.json, each card's leader-skill damage reduction.

Needs raw/mon_ja.json and raw/skill_ja.json from Mapaler's PADDashFormation
monsters-info folder, downloaded by hand. Shields are decoded from skill params,
never from the description text (激減 carries no number).

Run: python tools/make_card_shields.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CARDS_FILE = ROOT / "raw" / "mon_ja.json"
SKILLS_FILE = ROOT / "raw" / "skill_ja.json"
OUT_FILE = ROOT / "site" / "data" / "card_shields.json"

ATTRS = ["Fire", "Water", "Wood", "Light", "Dark"]
CONTAINER = 138
# Shield type -> index of its percent. Its condition (combos, shapes, colours) is treated as met.
CONDITIONAL = {16: 0, 151: 2, 169: 2, 170: 3, 171: 6, 182: 3, 193: 3, 198: 2, 210: 1, 235: 4, 271: 2, 285: 2}
SHIELD_TEXT = re.compile(r"ダメージを[^。、]*?(軽減|激減|半減)")
CHECK = {10981: [{"pct": 75}]}


def _param(skill: dict[str, Any], i: int) -> int:
    params = skill.get("params") or []
    value = params[i] if i < len(params) else 0
    return value if isinstance(value, int) else 0


def _from_mask(mask: int) -> list[str]:
    return [attr for bit, attr in enumerate(ATTRS) if mask >> bit & 1]


def _from_indexes(indexes: list[int]) -> list[str]:
    out: list[str] = []
    for i in indexes:
        if 0 <= i < len(ATTRS) and ATTRS[i] not in out:
            out.append(ATTRS[i])
    return out


def decode_one(skill: dict[str, Any]) -> dict[str, Any] | None:
    t = skill.get("type")
    extra: dict[str, Any] = {}
    if t in CONDITIONAL:
        pct = _param(skill, CONDITIONAL[t])
    elif t == 17:
        pct = _param(skill, 1)
        extra = {"enemy": _from_indexes([_param(skill, 0)])}
    elif t == 36:
        pct = _param(skill, 2)
        extra = {"enemy": _from_indexes([_param(skill, 0), _param(skill, 1)])}
    elif t in (129, 163):
        pct = _param(skill, 6)
        mask = _param(skill, 5)
        if mask and mask != 31:
            extra = {"enemy": _from_mask(mask)}
    elif t == 38:
        threshold, pct = _param(skill, 0), _param(skill, 2)
        extra = {"hp_at_least": 100} if threshold >= 100 else {"hp_at_most": threshold}
    elif t == 43:
        pct = _param(skill, 2)
        extra = {"hp_at_least": _param(skill, 0)}
    elif t == 130:
        pct = _param(skill, 6)
        extra = {"hp_at_most": _param(skill, 0)}
    elif t == 131:
        pct = _param(skill, 6)
        extra = {"hp_at_least": _param(skill, 0)}
    elif t == 183:
        pct = _param(skill, 4)
        extra = {"hp_at_least": _param(skill, 2)}
    else:
        return None
    if not 0 < pct <= 100:
        return None
    return {"pct": pct, **extra}


def _get(skills: list[Any], skill_id: Any) -> dict[str, Any] | None:
    if isinstance(skill_id, int) and 0 <= skill_id < len(skills) and isinstance(skills[skill_id], dict):
        return skills[skill_id]
    return None


def sub_skills(skill_id: int, skills: list[Any], depth: int = 0) -> list[dict[str, Any]]:
    skill = _get(skills, skill_id)
    if not skill:
        return []
    if skill.get("type") == CONTAINER and depth < 3:
        out: list[dict[str, Any]] = []
        for i in skill.get("params") or []:
            out += sub_skills(i, skills, depth + 1)
        return out
    return [skill]


def leader_shields(skill_id: int, skills: list[Any]) -> list[dict[str, Any]]:
    return [s for s in (decode_one(p) for p in sub_skills(skill_id, skills)) if s]


def _load_list(path: Path, key: str) -> list[Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get(key) or data.get(key + "s") or list(data.values())
    return data


def main() -> None:
    for path in (CARDS_FILE, SKILLS_FILE):
        if not path.exists():
            raise SystemExit(f"not found: {path}")
    cards = _load_list(CARDS_FILE, "card")
    skills = _load_list(SKILLS_FILE, "skill")

    out: dict[str, list[dict[str, Any]]] = {}
    leader_ids: set[int] = set()
    for card in cards:
        if not isinstance(card, dict) or not isinstance(card.get("id"), int):
            continue
        lid = card.get("leaderSkillId")
        if not lid:
            continue
        leader_ids.add(lid)
        shields = leader_shields(lid, skills)
        if shields:
            out[str(card["id"])] = shields

    missed, examples = Counter(), {}
    for lid in leader_ids:
        skill = _get(skills, lid)
        if not skill or not SHIELD_TEXT.search(skill.get("description", "")):
            continue
        if leader_shields(lid, skills):
            continue
        subs = sub_skills(lid, skills)
        sig = tuple(sorted(p.get("type") for p in subs))
        missed[sig] += 1
        examples.setdefault(sig, ([(p.get("type"), p.get("params")) for p in subs],
                                  skill.get("description", "").replace("\n", "")[:140]))

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    names_src = ROOT / "card_names.json"
    if names_src.exists():
        (OUT_FILE.parent / "card_names.json").write_text(names_src.read_text(encoding="utf-8"), encoding="utf-8")
        print("site/data/card_names.json copied")
    ordered = {k: out[k] for k in sorted(out, key=int)}
    OUT_FILE.write_text(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{OUT_FILE.relative_to(ROOT)}: {len(out)} cards with a shield")
    for card_id, expected in CHECK.items():
        got = out.get(str(card_id))
        print(f"check {card_id}: {got} {'ok' if got == expected else 'EXPECTED ' + str(expected)}")
    print(f"leaders whose text mentions a shield but decoded nothing: {sum(missed.values())}")
    for sig, n in missed.most_common(10):
        subs, desc = examples[sig]
        print(f"  {n} × types {sig}: {subs} | {desc}")


if __name__ == "__main__":
    main()
