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

// The working, one line per string: which card gave which shield, then the maths.
export function explainEffectiveHp(teamHp, sources) {
  const lines = [];
  const all = [];
  for (const source of sources) {
    if (!source.shields.length) {
      lines.push(`${source.role} ${who(source)}: no leader shield`);
      continue;
    }
    for (const shield of source.shields) {
      lines.push(`${source.role} ${who(source)}: ${describe(shield)}`);
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
