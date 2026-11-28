// Leader/helper shield maths. No DOM, so pytest can run it through node.

export function shieldAppliesAt(shield, hpPct) {
  if (shield.hp_at_least != null && hpPct < shield.hp_at_least) return false;
  if (shield.hp_at_most != null && hpPct > shield.hp_at_most) return false;
  return true;
}

// Effective HP rounds down. The tiny tolerance stops float noise (99,999.99999…) losing a whole point.
export const floorHp = (n) => Math.floor(n + 1e-6);

// Shields multiply: two 50% shields are 75%, not 100%.
export function reductionAt(shields, hpPct) {
  let taken = 1;
  for (const shield of shields) {
    if (shieldAppliesAt(shield, hpPct)) taken *= 1 - shield.pct / 100;
  }
  return 1 - taken;
}

// Lowest and highest effective HP across every HP state the shields care about.
export function effectiveHpRange(teamHp, shields) {
  if (!(teamHp > 0)) return null;
  let low = null;
  let high = null;
  for (let point = 1; point <= 100; point++) {
    const reduction = reductionAt(shields, point);
    const entry = {
      hp: reduction >= 1 ? Infinity : floorHp(teamHp / (1 - reduction)),
      pct: Math.round(reduction * 1000) / 10,
    };
    if (!low || entry.hp < low.hp) low = entry;
    if (!high || entry.hp > high.hp) high = entry;
  }
  return { low: low.hp, high: high.hp, lowPct: low.pct, highPct: high.pct };
}

const whole = (n) => floorHp(n).toLocaleString("en-US");
const dec = (n) => String(+n.toFixed(6));

function describe(shield) {
  const parts = [`${shield.pct}% shield`];
  if (shield.hp_at_least === 100) parts.push("at full HP");
  else if (shield.hp_at_least != null) parts.push(`at ${shield.hp_at_least}% HP or above`);
  if (shield.hp_at_most != null) parts.push(`at ${shield.hp_at_most}% HP or below`);
  if (shield.enemy) parts.push(`vs ${shield.enemy.join("/")} enemies (counted on every floor)`);
  return parts.join(" ");
}

const who = (source) => (source.name ? `${source.name} (${source.card})` : `card ${source.card}`);

const sourceLabel = (source) => (source.card == null ? source.role : `${source.role} ${who(source)}`);

// Larger shield replaces the looping one, so it only matters for hits the looping shield can't take.
export function survivalAlert(damage, effectiveHp, largerHp = null, halvesMaxHp = false) {
  if (!Number.isFinite(damage) || !(effectiveHp > 0)) return null;
  const share = halvesMaxHp ? 0.5 : 1;
  if (damage < effectiveHp * share) return null;
  if (largerHp != null && damage < largerHp * share) return "Larger shield needed";
  return "Can't survive";
}

// The working, one line per string: which card gave which shield, then the maths.
export function explainEffectiveHp(teamHp, sources) {
  const lines = [];
  const all = [];
  for (const source of sources) {
    if (!source.shields.length) {
      lines.push(`${sourceLabel(source)}: no leader shield`);
      continue;
    }
    for (const shield of source.shields) {
      lines.push(`${sourceLabel(source)}: ${describe(shield)}`);
      all.push(shield);
    }
  }
  if (!all.length) return lines;

  const runs = [];
  for (let hp = 1; hp <= 100; hp++) {
    const active = [];
    all.forEach((shield, i) => { if (shieldAppliesAt(shield, hp)) active.push(i); });
    const key = active.join(",");
    const last = runs[runs.length - 1];
    if (last && last.key === key) last.to = hp;
    else runs.push({ key, from: hp, to: hp, active: active.map((i) => all[i]) });
  }

  const results = [];
  for (const run of runs) {
    const prefix = runs.length > 1
      ? `At ${run.from === run.to ? run.from : `${run.from}–${run.to}`}% HP: `
      : "";
    if (!run.active.length) {
      lines.push(`${prefix}no shield`);
      if (teamHp > 0) {
        lines.push(`Effective HP = ${whole(teamHp)}`);
        results.push(teamHp);
      }
      continue;
    }
    const fractions = run.active.map((s) => dec(s.pct / 100));
    const taken = run.active.reduce((t, s) => t * (1 - s.pct / 100), 1);
    const reduction = 1 - taken;
    if (run.active.length === 1) {
      lines.push(`${prefix}Effective Shield = ${dec(reduction * 100)}%`);
    } else {
      const product = fractions.map((f) => `(1 − ${f})`).join(" × ");
      lines.push(`${prefix}Effective Shield = 1 − ${product} = 1 − ${dec(taken)} = ${dec(reduction)} (${dec(reduction * 100)}%)`);
    }
    if (teamHp > 0) {
      if (taken <= 0) {
        lines.push("Effective HP: no damage taken (100% shield)");
        results.push(Infinity);
      } else {
        const effective = teamHp / taken;
        lines.push(`Effective HP = ${whole(teamHp)} ÷ (1 − ${dec(reduction)}) = ${whole(teamHp)} ÷ ${dec(taken)} = ${whole(effective)}`);
        results.push(effective);
      }
    }
  }
  if (runs.length > 1 && results.length) {
    const lowest = Math.min(...results);
    lines.push(`Shield needed uses the lowest: ${Number.isFinite(lowest) ? whole(lowest) : "no damage taken"}`);
  }
  return lines;
}

// A failed puzzle lesson is the player's choice, not a hit to plan HP around.
// Same test as merge.py: a lesson_fail timing, or the ≤ combos branch of an enemy that also has a ≥ combos branch.
export function isPuzzleFail(action, enemyActions = []) {
  if (action.timing_kind === "lesson_fail" || action.when === "Puzzle lesson failed") return true;
  if (action.timing_kind !== "combo_le") return false;
  return enemyActions.some((other) => other.timing_kind === "combo_ge");
}

// Enrages you only meet by being slow: a Turn 3+ timer, or a leave-N-alive trigger.
export const SLOW_ENRAGE_TURN = 3;
const ATK_UP = new Set(["Enrage", "Enemy ATK up"]);

export function isSlowEnrage(action) {
  if (!(action.tags || []).some((tag) => ATK_UP.has(tag))) return false;
  if (action.timing_kind === "remaining_eq" || action.timing_kind === "remaining_le") return true;
  const step = enrageStep(action);
  return step !== null && step >= SLOW_ENRAGE_TURN;
}

// Which of the enemy's turns a numbered move lands on: Turn 3, Action 3, Normal action 3, or move 3 of an in-order set.
const STEP_KINDS = new Set(["turn", "nth_action", "normal", "sequence"]);
function enrageStep(action) {
  if (!STEP_KINDS.has(action.timing_kind)) return null;
  const match = /(?:Turn|Action|Normal action) (\d+)/.exec(action.when || "");
  if (match) return Number(match[1]);
  return Number.isFinite(action.order) ? action.order : null;
}

// The damage a hit is checked at; null leaves it out of the checks.
export function survivalDamage(action, enemyActions = []) {
  if (isSlowEnrage(action)) return null;
  const enrages = enemyActions.filter((other) => (other.tags || []).some((tag) => ATK_UP.has(tag)));
  if (enrages.length && enrages.every(isSlowEnrage)) {
    if (action.already_enraged) return null;
    const base = Number.isFinite(action.normal_hit) ? action.normal_hit : action.hit;
    return Number.isFinite(base) ? base : null;
  }
  const hits = [action.hit, action.enraged_hit].filter(Number.isFinite);
  return hits.length ? Math.max(...hits) : null;
}
