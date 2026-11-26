export const ATTRIBUTE_NAMES = ["Fire", "Water", "Wood", "Light", "Dark"];
const BILLION = 1e9;
const EPSILON = 1e-9;
const BEATS = { Fire: "Wood", Wood: "Water", Water: "Fire", Light: "Dark", Dark: "Light" };
const ORB_COLORS = new Set([...ATTRIBUTE_NAMES, "Heart", "Jammer", "Bomb", "Poison", "Mortal poison"]);

export function parseBillions(text) {
  const match = /^(\d+)\s*b?$/i.exec(String(text ?? "").trim());
  if (!match) return null;
  const value = Number(match[1]) * BILLION;
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function attributeMultiplier(attacker, defender) {
  if (!defender) return 1;
  if (BEATS[attacker] === defender) return 2;
  if (BEATS[defender] === attacker) return 0.5;
  return 1;
}

export function halvedAttributes(traits) {
  const halved = new Set();
  for (const trait of traits || []) {
    const match = /half damage from (.+)$/i.exec(String(trait));
    if (!match) continue;
    for (const name of ATTRIBUTE_NAMES) {
      if (new RegExp(`\\b${name}\\b`).test(match[1])) halved.add(name);
    }
  }
  return [...halved];
}

export function effectiveDamage(team, defender, absorbed = [], halved = []) {
  let total = 0;
  for (const [attribute, damage] of Object.entries(team || {})) {
    if (!Number.isFinite(damage) || damage <= 0 || absorbed.includes(attribute)) continue;
    const resist = halved.includes(attribute) ? 0.5 : 1;
    total += damage * attributeMultiplier(attribute, defender) * resist;
  }
  return total;
}

export function floorTurns(enemies, team, absorb = { colors: [], turns: 0 }, maxTurns = 99) {
  const segments = [];
  for (const enemy of enemies || []) {
    const [main, sub] = enemy.attributes || [];
    const halved = enemy.halved || [];
    segments.push({ hp: enemy.hp / 2, attribute: main, halved });
    segments.push({ hp: enemy.hp / 2, attribute: sub || main, halved });
  }
  let turn = 0;
  let index = 0;
  let left = segments.length ? segments[0].hp : 0;
  while (index < segments.length) {
    if (turn >= maxTurns) return { turns: maxTurns, capped: true };
    turn += 1;
    const absorbed = turn <= (absorb?.turns || 0) ? absorb.colors || [] : [];
    let budget = 1;
    while (budget > EPSILON && index < segments.length) {
      const segment = segments[index];
      const rate = effectiveDamage(team, segment.attribute, absorbed, segment.halved);
      if (rate <= 0) break;
      const needed = left / rate;
      if (needed <= budget + EPSILON) {
        budget -= needed;
        index += 1;
        left = index < segments.length ? segments[index].hp : 0;
      } else {
        left -= rate * budget;
        budget = 0;
      }
    }
  }
  return { turns: Math.max(1, turn), capped: false };
}

export function colorsIn(details) {
  const colors = new Set();
  let all = false;
  for (const detail of details || []) {
    for (const part of String(detail).split(/\s+-\s+|,\s*|\(|\)/)) {
      const token = part.trim();
      if (/^all colou?rs$/i.test(token)) all = true;
      else if (ORB_COLORS.has(token)) colors.add(token);
    }
  }
  return { colors, all };
}

export function affectsTeam(tag, details, teamColors) {
  if (!teamColors || teamColors.size === 0) return false;
  const { colors, all } = colorsIn(details);
  if (tag === "Attribute absorb" || tag === "Unmatchable") {
    return all || [...teamColors].some((color) => colors.has(color));
  }
  if (tag === "Roulette") {
    if (all || colors.size === 0) return false;
    return [...teamColors].some((color) => !colors.has(color));
  }
  return false;
}

export function teamTotalLabel(team) {
  const total = Object.values(team || {}).reduce(
    (sum, value) => sum + (Number.isFinite(value) ? value : 0),
    0,
  );
  return total > 0 ? `Total: ${Math.round(total / BILLION)}B` : null;
}
