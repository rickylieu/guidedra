import { allMechanics, filterFloors, formatFilterStatus } from "./filters.mjs";
import { actionTextForGroup, groupFloorActions } from "./floor-actions.mjs";
import {
  ATTRIBUTE_NAMES,
  affectsTeam,
  effectiveDamage,
  floorTurns,
  halvedAttributes,
  parseBillions,
  teamTotalLabel,
} from "./team-damage.mjs";

const dungeonSelect = document.getElementById("dungeon-select");
const teamHpInput = document.getElementById("team-hp");
const loadStatus = document.getElementById("load-status");
const errorPanel = document.getElementById("error-panel");
const guideContent = document.getElementById("guide-content");
const floorFilter = document.getElementById("floor-filter");
const floorFilterStatus = document.getElementById("floor-filter-status");
const clearFloorFilter = document.getElementById("clear-floor-filter");
const selectAllMechanicsButton = document.getElementById("select-all-mechanics");
const STORAGE_KEY = "pad-dungeon-guide-team-hp";
const AVERAGE_DAMAGE_KEY = "pad-dungeon-guide-average-damage";
const TEAM_DAMAGE_KEY = "pad-dungeon-guide-team-damage";
const SPLIT_CLERIC_KEY = "pad-dungeon-guide-split-cleric";
const DEBUG_MODE = new URL(window.location.href).searchParams.get("debug") === "1";
const DAMAGE_CAP_TAG = "Damage cap set";
const DEFAULT_TURNS_PER_FLOOR = 2;
const MAX_TURNS_PER_FLOOR = 99;
const MIN_TURNS_WITH_RESOLVE = 2;
const RESOLVE_TAGS = new Set(["Resolve", "Super resolve"]);
const BILLION = 1e9;
const PUZZLE_LESSON_TIMING_KINDS = new Set([
  "after_lesson",
  "lesson_pass",
  "lesson_fail",
]);
const PUZZLE_LESSON_WHENS = new Set([
  "After the puzzle lesson",
  "Puzzle lesson passed",
  "Puzzle lesson failed",
]);
const PUZZLE_EXEMPT_TAGS = new Set(["Resolve", "Super resolve", "Invade"]);

let dungeonIndex = [];
let currentDungeon = null;
let selectedMechanics = new Set();
let cardElements = {};
const ATTRIBUTES = new Set(ATTRIBUTE_NAMES);
const ATTRIBUTE_COLORS = {
  Fire: "229, 83, 61",
  Water: "61, 139, 229",
  Wood: "63, 174, 90",
  Light: "229, 194, 61",
  Dark: "155, 89, 208",
};

const SUMMARY_GROUPS = [
  {
    title: "Damage checks",
    mechanics: ["Damage void", "Damage absorb", "Attribute absorb"],
  },
  {
    title: "Cleric needs",
    mechanics: ["Bind", "Awoken bind", "Unmatchable"],
  },
];

const SKILL_PLANS = [
  {
    title: "Damage absorb skill",
    mechanics: ["Damage absorb"],
    lasting: true,
  },
  {
    title: "Attribute absorb skill",
    mechanics: ["Attribute absorb"],
    lasting: true,
    colors: true,
  },
  {
    title: "Damage void skill",
    mechanics: ["Damage void"],
    lasting: true,
  },
];

const CLERIC_PLAN = {
  title: "Cleric",
  mechanics: ["Awoken bind", "Unmatchable"],
  lasting: false,
};

const SPLIT_CLERIC_PLANS = [
  {
    title: "Cleric (Awoken bind)",
    mechanics: ["Awoken bind"],
    lasting: false,
  },
  {
    title: "Cleric (Unmatchable)",
    mechanics: ["Unmatchable"],
    lasting: false,
  },
];

const skillPlanSection = element("section", "summary-section skill-plan");
const skillPlanNote = element("p", "muted");
const skillPlanLines = element("div", "skill-plan-lines");
const averageDamageInput = element("input", teamHpInput.className);
averageDamageInput.type = "text";
averageDamageInput.inputMode = "numeric";
averageDamageInput.id = "average-damage";
averageDamageInput.placeholder = "e.g. 35";
averageDamageInput.autocomplete = "off";
const averageDamageLabel = element(
  "label",
  document.querySelector('label[for="team-hp"]')?.className || "",
  "Average damage per turn (billions) ",
);
averageDamageLabel.htmlFor = "average-damage";
const averageDamageField = element("p", "skill-plan-input");
const averageDamageTotal = element("span", "average-damage-total");
averageDamageTotal.style.display = "none";
averageDamageField.append(averageDamageLabel, averageDamageInput, averageDamageTotal);
const teamDamageInputs = new Map();
const teamDamageField = element("div", "team-attributes");
teamDamageField.append(
  element(
    "p",
    "muted",
    "Damage per turn by attribute (billions). Leave an attribute blank if your team doesn't hit with it.",
  ),
);
for (const name of ATTRIBUTE_NAMES) {
  const input = element("input", `${teamHpInput.className} team-attribute-input`);
  input.type = "text";
  input.inputMode = "numeric";
  input.id = `team-${name.toLowerCase()}`;
  input.placeholder = "0";
  input.autocomplete = "off";
  const label = element("label", `team-attribute attr-${name.toLowerCase()}`, `${name} `);
  label.htmlFor = input.id;
  const wrap = element("span", "team-attribute-field");
  wrap.append(label, input);
  teamDamageField.append(wrap);
  teamDamageInputs.set(name, input);
}
const splitClericInput = element("input");
splitClericInput.type = "checkbox";
splitClericInput.id = "split-cleric";
const splitClericLabel = element(
  "label",
  "",
  " Show Awoken bind and Unmatchable separately",
);
splitClericLabel.htmlFor = "split-cleric";
const splitClericField = element("p", "skill-plan-input");
splitClericField.append(splitClericInput, splitClericLabel);
skillPlanSection.append(
  element("h3", "", "Skill plan"),
  averageDamageField,
  teamDamageField,
  splitClericField,
  skillPlanNote,
  skillPlanLines,
);

function activeSkillPlans() {
  return splitClericInput.checked
    ? [...SKILL_PLANS, ...SPLIT_CLERIC_PLANS]
    : [...SKILL_PLANS, CLERIC_PLAN];
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return "";
  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumSignificantDigits: 3,
  }).format(value);
}

function safeHttpUrl(value) {
  if (typeof value !== "string" || value.trim() === "") return null;
  try {
    const url = new URL(value, window.location.href);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

function showError(message) {
  loadStatus.hidden = true;
  errorPanel.hidden = false;
  errorPanel.textContent = message;
  guideContent.hidden = true;
}

function updateLocation(slug) {
  const url = new URL(window.location.href);
  url.searchParams.set("d", slug);
  window.history.replaceState(null, "", url);
}

const LEADER_CARD_KEY = "pad-dungeon-guide-leader-card";
const HELPER_CARD_KEY = "pad-dungeon-guide-helper-card";
let cardShields = {};
let cardNames = {};
let effectiveHpRange = null;
let explainEffectiveHp = null;
const [leaderLabel, leaderInput] = cardNumberInput("leader-card", "Leader card #", LEADER_CARD_KEY);
const [helperLabel, helperInput] = cardNumberInput("helper-card", "Helper card #", HELPER_CARD_KEY);
const effectiveHpNote = document.createElement("div");
effectiveHpNote.className = "effective-hp";
const teamHpLabel = document.querySelector('label[for="team-hp"]');
const teamPanel = document.createElement("div");
teamPanel.className = "team-panel";
const teamFields = document.createElement("div");
teamFields.className = "team-fields";
const teamField = (...nodes) => {
  const wrap = document.createElement("span");
  wrap.className = "team-field";
  wrap.append(...nodes.filter(Boolean));
  return wrap;
};
(teamHpLabel || teamHpInput).before(teamPanel);
teamFields.append(
  teamField(teamHpLabel, teamHpInput),
  teamField(leaderLabel, leaderInput),
  teamField(helperLabel, helperInput),
);
teamPanel.append(teamFields, effectiveHpNote);
Promise.all([
  import("./team-shield.mjs"),
  fetch("data/card_shields.json").then((response) => (response.ok ? response.json() : {})),
  fetch("data/card_names.json").then((response) => (response.ok ? response.json() : {})),
])
  .then(([shieldMaths, data, names]) => {
    effectiveHpRange = shieldMaths.effectiveHpRange;
    explainEffectiveHp = shieldMaths.explainEffectiveHp;
    cardShields = data || {};
    cardNames = names || {};
    teamHpInput.dispatchEvent(new Event("input"));
  })
  .catch(() => {});

function cardNumberInput(id, text, key) {
  const label = document.createElement("label");
  label.htmlFor = id;
  label.className = document.querySelector('label[for="team-hp"]')?.className || "";
  label.textContent = text;
  const input = document.createElement("input");
  Object.assign(input, { id, type: "number", min: "1", step: "1", inputMode: "numeric", placeholder: "Optional" });
  input.className = teamHpInput.className;
  input.value = window.localStorage.getItem(key) || "";
  input.addEventListener("input", () => {
    if (input.value.trim() === "") window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, input.value);
    teamHpInput.dispatchEvent(new Event("input"));
  });
  return [label, input];
}

function cardSource(role, input) {
  const value = input.value.trim();
  if (!value) return null;
  const card = Number(value);
  const entry = cardNames[String(card)];
  const name = typeof entry === "string" ? entry : entry?.name_en || entry?.name || null;
  return { role, card, name, shields: cardShields[String(card)] || [] };
}

function showEffectiveHp(raw, sources) {
  const lines = explainEffectiveHp && sources.length ? explainEffectiveHp(raw, sources) : [];
  effectiveHpNote.replaceChildren(...lines.map((line) => element("div", "effective-hp-line", line)));
}

function selectedTeamHp() {
  const raw = rawTeamHp();
  const sources = [cardSource("Leader", leaderInput), cardSource("Helper", helperInput)].filter(Boolean);
  const shields = sources.flatMap((source) => source.shields);
  const range = raw === null || !effectiveHpRange ? null : effectiveHpRange(raw, shields);
  showEffectiveHp(raw, sources);
  return range ? range.low : raw;
}

function rawTeamHp() {
  const value = Number(teamHpInput.value);
  return teamHpInput.value.trim() !== "" && Number.isFinite(value) && value > 0
    ? value
    : null;
}

const parseDamage = parseBillions;

function teamDamage() {
  const team = {};
  for (const [name, input] of teamDamageInputs) {
    const value = parseBillions(input.value);
    if (value !== null) team[name] = value;
  }
  return Object.keys(team).length ? team : null;
}

function teamTotal(team) {
  return Object.values(team || {}).reduce((sum, value) => sum + value, 0);
}

function teamColors() {
  return new Set(Object.keys(teamDamage() || {}));
}

function unreadableTeamInputs() {
  return [...teamDamageInputs]
    .filter(([, input]) => input.value.trim() !== "" && parseBillions(input.value) === null)
    .map(([name]) => name);
}

function syncAverageFromTeam() {
  const label = teamTotalLabel(teamDamage());
  averageDamageInput.style.display = label ? "none" : "";
  averageDamageTotal.style.display = label ? "" : "none";
  averageDamageTotal.textContent = label || "";
  if (!label) {
    averageDamageInput.value = window.localStorage.getItem(AVERAGE_DAMAGE_KEY) || "";
  }
}

function saveTeamDamage() {
  const saved = {};
  for (const [name, input] of teamDamageInputs) {
    if (input.value.trim() !== "") saved[name] = input.value.trim();
  }
  if (Object.keys(saved).length) {
    window.localStorage.setItem(TEAM_DAMAGE_KEY, JSON.stringify(saved));
  } else {
    window.localStorage.removeItem(TEAM_DAMAGE_KEY);
  }
}

function loadTeamDamage() {
  let saved = {};
  try {
    saved = JSON.parse(window.localStorage.getItem(TEAM_DAMAGE_KEY) || "{}") || {};
  } catch {
    saved = {};
  }
  for (const [name, input] of teamDamageInputs) {
    input.value = typeof saved[name] === "string" ? saved[name] : "";
  }
}

function formatMultiple(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function alertForAction(action, floor, teamHp) {
  const hit = action.hit;
  if (!Number.isFinite(hit)) return null;
  if (action.severity === "execute") return "Execute";
  if (action.severity === "large") {
    const multiple = Number.isFinite(action.severity_multiple)
      ? `${formatMultiple(action.severity_multiple)}× normal-hit median`
      : "";
    if (teamHp !== null) {
      const threshold = floor.halves_max_hp ? teamHp / 2 : teamHp;
      if (hit >= threshold) {
        return multiple ? `Shield needed (${multiple})` : "Shield needed";
      }
    }
    return multiple
      ? `Large hit (additional shield may be needed; ${multiple})`
      : "Large hit (additional shield may be needed)";
  }
  if (teamHp !== null) {
    const threshold = floor.halves_max_hp ? teamHp / 2 : teamHp;
    return hit >= threshold ? "Shield needed" : null;
  }
  return null;
}

function formatEffectDetail(detail) {
  return detail
    .replace(/\bfor (\d+) turns\b/g, (_, count) => {
      return `${count} ${count === "1" ? "turn" : "turns"}`;
    })
    .replace(/^for /, "");
}

function formatEffectDetails(details) {
  return (details || []).map(formatEffectDetail).join("; ");
}

function isDamageCapValue(name, detail) {
  return name === DAMAGE_CAP_TAG && detail.startsWith("cap ");
}

function damageCapValues(name, details) {
  return [...new Set(
    (details || [])
      .filter((detail) => isDamageCapValue(name, detail))
      .map((detail) => `to ${detail.slice(4)}`),
  )];
}

function displayMechanicName(name) {
  return name === DAMAGE_CAP_TAG ? "Damage cap changed" : name;
}

function visibleEffectDetails(name, details) {
  return [
    ...damageCapValues(name, details),
    ...(details || []).filter((detail) => !isDamageCapValue(name, detail)),
  ];
}

function allTagDetails(tag) {
  return [
    ...(tag?.details || []),
    ...(tag?.variants || []).flatMap((variant) => variant.details || []),
  ];
}

function actionDetailText(action) {
  return /\(([^)]*)\)/.exec(action.text || "")?.[1] || "";
}

function unresolvedEffectVariantIndexes(variants) {
  const unresolved = new Set();
  for (let first = 0; first < variants.length; first += 1) {
    for (let second = first + 1; second < variants.length; second += 1) {
      const left = variants[first];
      const right = variants[second];
      const sameEnemies =
        JSON.stringify([...(left.enemies || [])].sort()) ===
        JSON.stringify([...(right.enemies || [])].sort());
      if (
        left.when === right.when &&
        sameEnemies &&
        JSON.stringify(left.details || []) !== JSON.stringify(right.details || [])
      ) {
        unresolved.add(first);
        unresolved.add(second);
      }
    }
  }
  return unresolved;
}

function formatEffectVariants(
  tagName,
  effect,
  hideDamageVoidThreshold = true,
) {
  const grouped = new Map();
  const variants = effect?.variants || [];
  const unresolvedVariants = unresolvedEffectVariantIndexes(variants);
  for (const [index, variant] of variants.entries()) {
    const details = (variant.details || []).filter((detail) => {
      const isDamageVoidThreshold =
        /^\d+(?:\.\d+)?(?:K|M|B|T)? or more$/i.test(detail);
      return !(
        (hideDamageVoidThreshold && tagName === "Damage void" && isDamageVoidThreshold) ||
        isDamageCapValue(tagName, detail)
      );
    });
    const capValue = damageCapValues(tagName, variant.details).join(", ");
    const enemyLabel = variant.enemies?.length
      ? `on ${variant.enemies.join(", ")}`
      : null;
    const parts = [
      capValue,
      variant.when,
      formatEffectDetails(details),
      enemyLabel,
    ].filter((part) => part && part !== "Unknown timing");
    const text = parts.join(" · ");
    if (!text) continue;
    if (!grouped.has(text)) {
      grouped.set(text, { sources: new Set(), unresolved: false });
    }
    const group = grouped.get(text);
    group.unresolved ||= unresolvedVariants.has(index);
    for (const source of variant.sources || []) group.sources.add(source);
  }
  const formatted = [...grouped].map(([text, group]) => {
    const sourceList = [...group.sources].sort();
    return DEBUG_MODE && group.unresolved && sourceList.length
      ? `${text} (${sourceList.join(", ")})`
      : text;
  });
  if (effect?.not_reported_for?.length) {
    formatted.push(`Not reported for ${effect.not_reported_for.join(", ")}`);
  }
  return formatted;
}

function formatAlternativeAttributeAbsorb(effect, floor) {
  const variantsByEnemy = new Map();
  const variants = effect?.variants || [];
  const unresolvedVariants = unresolvedEffectVariantIndexes(variants);
  for (const [index, variant] of variants.entries()) {
    for (const enemy of variant.enemies || []) {
      if (!variantsByEnemy.has(enemy)) variantsByEnemy.set(enemy, []);
      variantsByEnemy.get(enemy).push({ index, variant });
    }
  }
  if (!variantsByEnemy.size) return null;

  const enemyOrder = new Map(
    (floor.enemies || []).map((enemy, index) => [enemy.name, index]),
  );
  const enemyDetails = [...variantsByEnemy]
    .sort(([first], [second]) =>
      (enemyOrder.get(first) ?? Number.MAX_SAFE_INTEGER) -
      (enemyOrder.get(second) ?? Number.MAX_SAFE_INTEGER),
    )
    .map(([enemy, variants]) => {
      const formatted = [...variants]
        .sort(
          (first, second) =>
            Number((second.variant.details || []).some((detail) => !detail.startsWith("for "))) -
            Number((first.variant.details || []).some((detail) => !detail.startsWith("for "))),
        )
        .map(({ index, variant }) => {
          const duration = (variant.details || [])
            .find((detail) => detail.startsWith("for "))
            ?.replace(/^for /, "");
          const colors = (variant.details || [])
            .filter((detail) => !detail.startsWith("for "))
            .join(", ");
          const sources =
            DEBUG_MODE && unresolvedVariants.has(index) && variant.sources?.length
              ? ` (${variant.sources.join(", ")})`
              : "";
          if (colors && duration) {
            return `${colors} (${duration})${sources}`;
          }
          return `${[colors, duration].filter(Boolean).join(" ")}${sources}`;
        });
      return `${enemy}: ${formatted.join("; ")}`;
    });
  const total = (floor.enemies || []).length;
  const notReported = effect.not_reported_for?.length
    ? `; not reported for ${effect.not_reported_for.join(", ")}`
    : "";
  return `${variantsByEnemy.size}/${total} possible enemies have Attribute absorb — ${
    enemyDetails.join("; ")
  }${notReported}`;
}

function renderRules(data) {
  const container = document.getElementById("dungeon-rules");
  container.replaceChildren();
  if (data.rules?.battles !== null && data.rules?.battles !== undefined) {
    container.append(element("span", "rule-chip", `${data.rules.battles} battles`));
  }
  if (data.rules?.stamina !== null && data.rules?.stamina !== undefined) {
    container.append(element("span", "rule-chip", `${data.rules.stamina} stamina`));
  }
  for (const note of data.rules?.notes || []) {
    container.append(element("span", "rule-chip", note));
  }
}

function primarySourceName(data) {
  return data.sources?.[0]?.name || "";
}

function floorActions(floor) {
  return (floor.enemies || []).flatMap((enemy) => enemy.actions || []);
}

function isPreemptiveWhen(when) {
  return !when || when === "Preemptive";
}

function isPreemptiveAction(action) {
  return action.timing_kind === "preemptive" || isPreemptiveWhen(action.when);
}

function isAfterPuzzleLesson(action) {
  return (
    PUZZLE_LESSON_TIMING_KINDS.has(action.timing_kind) ||
    PUZZLE_LESSON_WHENS.has(action.when)
  );
}

function isPuzzleLessonFloor(floor) {
  return floorActions(floor).some(isAfterPuzzleLesson);
}

function actionTagNames(action) {
  return (action.tags || []).map((tag) =>
    typeof tag === "string" ? tag : tag?.name,
  );
}

function puzzleFloorTag(tag, actions) {
  if (PUZZLE_EXEMPT_TAGS.has(tag.name)) return tag;
  if (tag.variants?.length) {
    const variants = tag.variants.filter(
      (variant) => !isPreemptiveWhen(variant.when),
    );
    return variants.length ? { ...tag, variants } : null;
  }
  const tagged = actions.filter((action) =>
    actionTagNames(action).includes(tag.name),
  );
  return tagged.length && tagged.every(isPreemptiveAction) ? null : tag;
}

function withoutPuzzleEffects(floor) {
  if (!isPuzzleLessonFloor(floor)) return floor;
  const actions = floorActions(floor);
  const tags = (floor.tags || [])
    .map((tag) => puzzleFloorTag(tag, actions))
    .filter(Boolean);
  return {
    ...floor,
    tags,
    halves_max_hp:
      Boolean(floor.halves_max_hp) &&
      tags.some((tag) => tag.name === "Max HP halved"),
  };
}

function withoutPuzzleLessonEffects(data) {
  const floors = (data.floors || []).map(withoutPuzzleEffects);
  const summary = {};
  for (const [tag, labels] of Object.entries(data.summary || {})) {
    const kept = (labels || []).filter((label) => {
      const floor = floors.find((entry) => entry.label === label);
      return !floor || (floor.tags || []).some((entry) => entry.name === tag);
    });
    if (kept.length) summary[tag] = kept;
  }
  return { ...data, floors, summary };
}

function effectDuration(details) {
  let longest = null;
  for (const detail of details || []) {
    const match = /^for (\d+) turns?$/.exec(detail);
    if (match) longest = Math.max(longest ?? 0, Number(match[1]));
  }
  return longest;
}

function floorAppear(floor) {
  return Number.isInteger(floor.appear) && floor.appear > 0 ? floor.appear : null;
}

function floorHp(floor) {
  const enemies = floor.enemies || [];
  const hps = enemies
    .map((enemy) => enemy.hp)
    .filter((hp) => Number.isFinite(hp) && hp > 0)
    .sort((first, second) => second - first);
  if (hps.length === 0) return null;
  const total = (values) => values.reduce((sum, hp) => sum + hp, 0);
  const appear = floorAppear(floor);
  if (appear !== null && appear < hps.length) return total(hps.slice(0, appear));
  if (appear !== null && enemies.length === 1) return hps[0] * appear;
  return total(hps);
}

function countedEnemies(floor) {
  const all = floor.enemies || [];
  const withHp = all
    .filter((enemy) => Number.isFinite(enemy.hp) && enemy.hp > 0)
    .sort((first, second) => second.hp - first.hp);
  if (withHp.length === 0) return null;
  const appear = floorAppear(floor);
  let picked = withHp;
  if (appear !== null && appear < withHp.length) {
    picked = withHp.slice(0, appear);
  } else if (appear !== null && all.length === 1) {
    picked = Array(appear).fill(withHp[0]);
  }
  return picked.map((enemy) => ({
    hp: enemy.hp,
    attributes: enemyAttributes(enemy),
    halved: halvedAttributes(enemy.traits),
  }));
}

function floorAbsorb(floor) {
  const tag = (floor.tags || []).find((entry) => entry.name === "Attribute absorb");
  if (!tag) return { colors: [], turns: 0 };
  const variants = tag.variants?.length
    ? tag.variants
    : [{ when: "Preemptive", details: tag.details || [] }];
  const colors = new Set();
  let turns = 0;
  for (const variant of variants) {
    if (!isPreemptiveWhen(variant.when)) continue;
    const found = (variant.details || [])
      .flatMap((detail) => detail.split(/,\s*/))
      .map((name) => name.trim())
      .filter((name) => ATTRIBUTES.has(name));
    if (found.length === 0) continue;
    for (const color of found) colors.add(color);
    turns = Math.max(turns, effectDuration(variant.details) ?? MAX_TURNS_PER_FLOOR);
  }
  return { colors: [...colors], turns };
}

function hasResolve(floor) {
  if ((floor.tags || []).some((tag) => RESOLVE_TAGS.has(tag.name))) return true;
  return (floor.enemies || []).some((enemy) =>
    (enemy.traits || []).some((trait) => /resolve/i.test(trait)),
  );
}

function invadeFloorNumbers(floor) {
  if (Array.isArray(floor.invade_floors) && floor.invade_floors.length) {
    return [...new Set(floor.invade_floors.filter(Number.isInteger))];
  }
  const match = /Floors?\s+([\d,\s]+)/.exec(floor.label || "");
  if (!match) return [];
  return [...new Set(
    match[1]
      .split(",")
      .map((part) => Number(part.trim()))
      .filter((number) => Number.isInteger(number) && number > 0),
  )];
}

function invadeScenarios(data) {
  const numbered = (data.floors || []).filter((floor) =>
    Number.isInteger(floor.number),
  );
  const scenarios = [{ invadeFloor: null, floors: numbered }];
  for (const invader of data.floors || []) {
    if (Number.isInteger(invader.number)) continue;
    for (const number of invadeFloorNumbers(invader)) {
      scenarios.push({
        invadeFloor: number,
        floors: [
          ...numbered.filter((floor) => floor.number !== number),
          {
            ...invader,
            number,
            label: `Floor ${number}`,
            assumedLabel: invader.label,
          },
        ],
      });
    }
  }
  return scenarios;
}

function unplacedInvades(data) {
  return (data.floors || []).filter(
    (floor) =>
      !Number.isInteger(floor.number) && invadeFloorNumbers(floor).length === 0,
  );
}

function buildTimeline(floors, averageDamage, team = null) {
  const timeline = new Map();
  const assumed = [];
  const stalled = [];
  const ordered = floors
    .filter((floor) => Number.isInteger(floor.number))
    .sort((first, second) => first.number - second.number);
  let nextTurn = 1;
  let previousNumber = 0;
  for (const floor of ordered) {
    if (timeline.has(floor.number)) continue;
    nextTurn +=
      Math.max(0, floor.number - previousNumber - 1) * DEFAULT_TURNS_PER_FLOOR;
    let turns = DEFAULT_TURNS_PER_FLOOR;
    const minimum = hasResolve(floor) ? MIN_TURNS_WITH_RESOLVE : 1;
    if (team) {
      const enemies = countedEnemies(floor);
      if (enemies === null) {
        assumed.push(floor.assumedLabel || floor.label);
      } else {
        const result = floorTurns(enemies, team, floorAbsorb(floor), MAX_TURNS_PER_FLOOR);
        turns = Math.max(minimum, result.turns);
        if (result.capped) stalled.push(floor.assumedLabel || floor.label);
      }
    } else if (averageDamage !== null) {
      const hp = floorHp(floor);
      if (hp === null) {
        assumed.push(floor.assumedLabel || floor.label);
      } else {
        turns = Math.min(
          MAX_TURNS_PER_FLOOR,
          Math.max(minimum, Math.ceil(hp / averageDamage)),
        );
      }
    }
    timeline.set(floor.number, { start: nextTurn, turns });
    nextTurn += turns;
    previousNumber = floor.number;
  }
  return { timeline, assumed, stalled };
}

function skillNeedsForFloor(floor, plan) {
  const needs = [];
  for (const tag of floor.tags || []) {
    if (!plan.mechanics.includes(tag.name)) continue;
    const variants = tag.variants?.length
      ? tag.variants
      : [{ when: "Preemptive", details: tag.details || [] }];
    for (const variant of variants) {
      const when = variant.when || "Preemptive";
      const timing = when === "Unknown timing" ? "" : when;
      const colors = (variant.details || []).filter(
        (detail) => !detail.startsWith("for "),
      );
      let reason = timing;
      if (plan.mechanics.length > 1) {
        reason = [tag.name, timing].filter(Boolean).join(" · ");
      } else if (plan.colors && colors.length) {
        reason = [timing, colors.join(", ")].filter(Boolean).join(" - ");
      }
      needs.push({
        reason,
        preemptive: when === "Preemptive",
        skippable: when !== "Preemptive" && when !== "Unknown timing",
        duration: effectDuration(variant.details),
        colors,
      });
    }
  }
  return needs;
}

function buildSkillPlan(floors, plan, timeline) {
  const turns = new Map();
  for (const floor of floors) {
    const span = Number.isInteger(floor.number)
      ? timeline.get(floor.number)
      : null;
    if (!span) continue;
    const needs = skillNeedsForFloor(floor, plan).filter(
      (need) => !(span.turns === 1 && need.skippable),
    );
    if (needs.length === 0) continue;
    const floorEnd = span.start + span.turns - 1;
    for (const need of needs) {
      const first = span.start + (need.preemptive ? 0 : Math.min(1, span.turns - 1));
      let last = first;
      if (plan.lasting) {
        last = need.duration === null
          ? floorEnd
          : Math.max(first, Math.min(floorEnd, first + need.duration - 1));
      }
      for (let turn = first; turn <= last; turn += 1) {
        if (!turns.has(turn)) {
          turns.set(turn, {
            floor,
            floorTurn: turn - span.start + 1,
            reasons: new Set(),
          });
        }
        if (need.reason) turns.get(turn).reasons.add(need.reason);
      }
    }
  }

  const runs = [];
  for (const turn of [...turns.keys()].sort((first, second) => first - second)) {
    const entry = turns.get(turn);
    const current = runs[runs.length - 1];
    if (plan.lasting && current && turn === current.end + 1) {
      current.end = turn;
      current.endFloor = entry.floor;
    } else {
      runs.push({
        start: turn,
        end: turn,
        startFloor: entry.floor,
        startFloorTurn: entry.floorTurn,
        endFloor: entry.floor,
        reasons: [...entry.reasons],
      });
    }
  }
  return runs;
}

function longestRun(runs) {
  return runs.reduce((best, run) =>
    run.end - run.start > best.end - best.start ? run : best,
  );
}

function tightestGap(runs) {
  let tightest = null;
  for (let index = 1; index < runs.length; index += 1) {
    const gap = runs[index].start - runs[index - 1].start;
    if (tightest === null || gap < tightest.gap) {
      tightest = {
        gap,
        from: runs[index - 1].startFloor,
        to: runs[index].startFloor,
      };
    }
  }
  return tightest;
}

function worstCaseSkillPlan(scenarios, plan) {
  const worst = { first: null, longest: null, tightest: null };
  for (const scenario of scenarios) {
    const runs = buildSkillPlan(scenario.floors, plan, scenario.timeline);
    if (runs.length === 0) continue;
    const { invadeFloor } = scenario;
    if (!worst.first || runs[0].start < worst.first.run.start) {
      worst.first = { run: runs[0], invadeFloor };
    }
    if (plan.lasting) {
      const run = longestRun(runs);
      if (
        !worst.longest ||
        run.end - run.start > worst.longest.run.end - worst.longest.run.start
      ) {
        worst.longest = { run, invadeFloor };
      }
    }
    const gap = tightestGap(runs);
    if (gap && (!worst.tightest || gap.gap < worst.tightest.gap)) {
      worst.tightest = { ...gap, invadeFloor };
    }
  }
  return worst;
}

function unplacedInvadeLabels(floors, plan) {
  const labels = [];
  for (const floor of floors) {
    const needs = skillNeedsForFloor(floor, plan);
    if (needs.length === 0) continue;
    const colors = plan.colors
      ? [...new Set(needs.flatMap((need) => need.colors))]
      : [];
    labels.push(
      colors.length ? `${floor.label} - ${colors.join(", ")}` : floor.label,
    );
  }
  return labels;
}

function formatFloorSpan(first, last) {
  return first === last
    ? first.label
    : `Floors ${first.number}–${last.number}`;
}

function withInvaderNote(items, invadeFloor) {
  const all = [...items];
  if (invadeFloor !== null) all.push(`invader on Floor ${invadeFloor}`);
  return all.length ? ` (${all.join("; ")})` : "";
}

function formatSkillPlanLine(plan, worst, unplacedLabels) {
  if (!worst.first) {
    return unplacedLabels.length
      ? `only on ${unplacedLabels.join("; ")}`
      : "not needed";
  }
  const { run: first, invadeFloor: firstInvade } = worst.first;
  const parts = [
    `first needed ${first.startFloor.label}, turn ${first.startFloorTurn}${
      withInvaderNote(first.reasons, firstInvade)
    }`,
  ];
  if (plan.lasting && worst.longest) {
    const { run, invadeFloor } = worst.longest;
    const length = run.end - run.start + 1;
    parts.push(
      `effect: ${length} ${length === 1 ? "turn" : "turns"}${
        withInvaderNote([formatFloorSpan(run.startFloor, run.endFloor)], invadeFloor)
      }`,
    );
  }
  if (worst.tightest) {
    const { gap, from, to, invadeFloor } = worst.tightest;
    const where = from === to
      ? `within ${from.label}`
      : `${from.label} → ${to.label}`;
    parts.push(`cooldown ≤ ${gap}${withInvaderNote([where], invadeFloor)}`);
  } else {
    parts.push("needed once");
  }
  if (unplacedLabels.length) {
    parts.push(`also on ${unplacedLabels.join("; ")}`);
  }
  return parts.join(" · ");
}

function updateSkillPlan() {
  skillPlanLines.replaceChildren();
  if (!currentDungeon) return;
  const team = teamDamage();
  const typed = averageDamageInput.value.trim();
  const averageDamage = team ? teamTotal(team) : parseDamage(typed);
  const scenarios = invadeScenarios(currentDungeon).map((scenario) => ({
    ...scenario,
    ...buildTimeline(scenario.floors, averageDamage, team),
  }));
  const assumed = [...new Set(scenarios.flatMap((scenario) => scenario.assumed))];
  const stalled = [...new Set(scenarios.flatMap((scenario) => scenario.stalled))];
  const unplaced = unplacedInvades(currentDungeon);
  const unreadable = unreadableTeamInputs();
  const notes = [];
  if (unreadable.length) {
    notes.push(
      `Couldn't read the ${unreadable.join(", ")} damage (enter a whole number of billions, like 12), so it is left out.`,
    );
  }
  if (averageDamage === null) {
    notes.push(
      typed === ""
        ? `Assumes every floor takes ${DEFAULT_TURNS_PER_FLOOR} turns. Enter average damage to count turns from enemy HP.`
        : `Couldn't read that damage (enter a whole number of billions, like 35), so every floor is assumed to take ${DEFAULT_TURNS_PER_FLOOR} turns.`,
    );
  } else {
    if (team) {
      notes.push(
        "Turns on a floor use your damage by attribute against each enemy's attribute (main above 50% HP, sub at or below): Fire > Wood > Water > Fire is ×2 / ×0.5, Light and Dark ×2 against each other, and an enemy that takes half damage from an attribute halves it.",
        "A colour in a preemptive Attribute absorb counts as 0 damage while the absorb lasts.",
      );
    } else {
      notes.push(`Turns on a floor = its enemy HP ÷ ${formatNumber(averageDamage)}, rounded up.`);
    }
    notes.push(
      `Floors with resolve or super resolve take at least ${MIN_TURNS_WITH_RESOLVE} turns.`,
      "Effects that aren't preemptive are left out on floors cleared in 1 turn.",
    );
    if (assumed.length) {
      notes.push(
        `No HP for ${assumed.join(", ")}: assumed ${DEFAULT_TURNS_PER_FLOOR} turns.`,
      );
    }
  }
  if (scenarios.length > 1) {
    notes.push(
      "The invader is tried on each floor it can appear on, in place of that floor's enemies; each line shows the worst case.",
    );
  }
  if (unplaced.length) {
    notes.push("Invaders with no known floor are not counted in the turns.");
  }
  skillPlanNote.textContent = notes.join(" ");
  if (averageDamage !== null && stalled.length) {
    const warning = element("p", "skill-plan-line skill-plan-stall");
    warning.append(
      element("strong", "", "Can't clear in time:"),
      ` ${stalled.join(", ")} (counted as ${MAX_TURNS_PER_FLOOR} turns)`,
    );
    skillPlanLines.append(warning);
  }
  for (const plan of activeSkillPlans()) {
    const line = element("p", "skill-plan-line");
    line.append(
      element("strong", "", plan.title),
      ` — ${formatSkillPlanLine(
        plan,
        worstCaseSkillPlan(scenarios, plan),
        unplacedInvadeLabels(unplaced, plan),
      )}`,
    );
    skillPlanLines.append(line);
  }
}

function applySummaryRisks() {
  const colors = teamColors();
  for (const item of document.querySelectorAll("#critical-summary li[data-mechanic]")) {
    let details = [];
    try {
      details = JSON.parse(item.dataset.details || "[]");
    } catch {
      details = [];
    }
    item.classList.toggle(
      "team-risk",
      affectsTeam(item.dataset.mechanic, details, colors),
    );
  }
}

function renderCriticalSummary(data) {
  const container = document.getElementById("critical-summary");
  container.replaceChildren();
  const summary = data.summary || {};
  const groupedMechanics = new Set(SUMMARY_GROUPS.flatMap((group) => group.mechanics));
  const groups = [
    ...SUMMARY_GROUPS,
    {
      title: "Other mechanics",
      mechanics: Object.keys(summary).filter((tag) => !groupedMechanics.has(tag)),
    },
  ];
  if (Object.keys(summary).length === 0) {
    container.append(element("p", "muted", "No critical mechanics found."));
    return;
  }
  container.append(skillPlanSection);
  updateSkillPlan();
  for (const group of groups) {
    const mechanics = group.mechanics.filter((tag) => summary[tag]?.length);
    if (mechanics.length === 0) continue;
    const section = element("section", "summary-section");
    section.append(element("h3", "", group.title));
    const grid = element("div", "summary-grid");
    for (const tag of mechanics) {
      const item = element("div", "summary-item");
      const mechanicName = displayMechanicName(tag);
      const button = element("button", "summary-mechanic", mechanicName);
      button.type = "button";
      button.dataset.mechanic = tag;
      button.setAttribute("aria-label", `Toggle ${mechanicName} floor filter`);
      button.setAttribute("aria-controls", "floors-list");
      button.setAttribute("aria-pressed", String(selectedMechanics.has(tag)));
      button.addEventListener("click", () => selectMechanic(tag));
      item.append(button);
      const floorList = element("ul", "summary-floor-list");
      for (const label of summary[tag]) {
        const floor = (data.floors || []).find((entry) => entry.label === label);
        const effect = floor?.tags?.find((entry) => entry.name === tag);
        const variants = formatEffectVariants(tag, effect);
        const fallbackDetails = tag === "Damage void"
          ? []
          : visibleEffectDetails(tag, effect?.details);
        const alternativeAbsorb =
          tag === "Attribute absorb" && floor?.one_of
            ? formatAlternativeAttributeAbsorb(effect, floor)
            : null;
        const details = alternativeAbsorb || (variants.length
          ? variants.join("; ")
          : formatEffectDetails(fallbackDetails));
        const floorLabel = floor?.one_of && !alternativeAbsorb
          ? `${label} (${floor.appear} of ${(floor.enemies || []).length} possible enemies)`
          : label;
        const entry = element(
          "li",
          "",
          details ? `${floorLabel} — ${details}` : `${floorLabel} — ${mechanicName}`,
        );
        entry.dataset.mechanic = tag;
        entry.dataset.details = JSON.stringify(allTagDetails(effect));
        floorList.append(entry);
      }
      item.append(floorList);
      grid.append(item);
    }
    section.append(grid);
    container.append(section);
  }
  selectAllMechanicsButton.disabled = Object.keys(summary).length === 0;
  syncMechanicControls();
  applySummaryRisks();
}

function selectMechanic(mechanic) {
  if (selectedMechanics.has(mechanic)) {
    selectedMechanics.delete(mechanic);
  } else {
    selectedMechanics.add(mechanic);
  }
  syncMechanicControls();
  if (currentDungeon) renderFloors(currentDungeon);
}

function syncMechanicControls() {
  for (const button of document.querySelectorAll(".summary-mechanic")) {
    button.setAttribute(
      "aria-pressed",
      String(selectedMechanics.has(button.dataset.mechanic)),
    );
  }
  const allSelected =
    currentDungeon !== null &&
    Object.keys(currentDungeon.summary || {}).length > 0 &&
    [...document.querySelectorAll(".summary-mechanic")].every((button) =>
      selectedMechanics.has(button.dataset.mechanic),
    );
  selectAllMechanicsButton.setAttribute("aria-pressed", String(allSelected));
}

function renderHitSummary(data) {
  const container = document.getElementById("hit-summary");
  container.replaceChildren();
  const teamHp = selectedTeamHp();
  const byFloor = new Map();
  if (Number.isFinite(data.normal_hit_baseline) && data.normal_hit_baseline > 0) {
    container.append(
      element(
        "p",
        "muted",
        `Median normal-hit baseline ${formatNumber(data.normal_hit_baseline)} · large hits ≥2× baseline · non-enraged executes >4× · enraged hits ≥2× stay visible as large hits`,
      ),
    );
  }
  const progression = data.damage_progression || {};
  if ((progression.ranges || []).length) {
    container.append(
      element(
        "p",
        "muted",
        `Normal-hit damage progression (enraged, execute, and anomalously low preemptive hits excluded; ranges split at changes over ${formatMultiple(progression.range_change_multiple)}×):`,
      ),
    );
    for (const range of progression.ranges) {
      let label = `${range.label} median damage ${formatNumber(range.median_hit)}`;
      if (Number.isFinite(range.min_hit) && Number.isFinite(range.max_hit)) {
        label += ` · range ${formatNumber(range.min_hit)}–${formatNumber(range.max_hit)}`;
      }
      if (Number.isFinite(range.increase_multiple)) {
        label += ` · increase ${formatMultiple(range.increase_multiple)}× from previous range (${formatNumber(range.increase_from_hit)})`;
      }
      container.append(element("p", "", label));
    }
    for (const floor of progression.missing_floors || []) {
      container.append(
        element(
          "p",
          "muted",
          `Floor ${floor}: No attacks found in data.`,
        ),
      );
    }
    for (const floor of progression.excluded_floors || []) {
      const hits = (floor.hits || []).map(formatNumber).join(", ");
      container.append(
        element(
          "p",
          "muted",
          `${floor.label}: ${hits} preemptive damage excluded as anomalously low before shields and team transformations.`,
        ),
      );
    }
    if (Number.isFinite(progression.invade_median_hit)) {
      container.append(
        element(
          "p",
          "",
          `Invade median damage ${formatNumber(progression.invade_median_hit)}`,
        ),
      );
    }
  }
  for (const floor of data.floors || []) {
    for (const enemy of floor.enemies || []) {
      for (const action of enemy.actions || []) {
        if (action.severity !== "large") continue;
        const threshold = floor.halves_max_hp ? teamHp / 2 : teamHp;
        if (teamHp !== null && action.hit < threshold) continue;
        if (Number.isFinite(action.hit)) {
          const current = byFloor.get(floor.label);
          if (!current || action.hit > current.hit) {
            byFloor.set(floor.label, {
              hit: action.hit,
              multiple: action.severity_multiple,
            });
          }
        }
      }
    }
  }
  if (byFloor.size === 0) {
    const message = teamHp === null
      ? "No large hits identified."
      : "No large hits exceed the current Team HP threshold.";
    container.append(element("p", "muted", message));
    return;
  }
  for (const [floor, hit] of byFloor) {
    const multiple = Number.isFinite(hit.multiple)
      ? `${formatMultiple(hit.multiple)}× normal-hit median`
      : null;
    const alertName = teamHp === null
      ? `Large hit${multiple ? ` (${multiple}; additional shield may be needed)` : " (additional shield may be needed)"}`
      : `Shield needed${multiple ? ` (${multiple})` : ""}`;
    container.append(element("p", "", `${alertName} · ${floor} · ${formatNumber(hit.hit)} damage`));
  }
}

function renderFloorTags(tags, primary) {
  const list = element("div", "tag-list");
  const colors = teamColors();
  for (const tag of tags || []) {
    const classes = ["tag"];
    if (tag.critical) classes.push("critical");
    const foundBy = tag.sources || [];
    if (!foundBy.includes(primary)) classes.push("not-primary");
    const risky = affectsTeam(tag.name, allTagDetails(tag), colors);
    if (risky) classes.push("team-risk");
    const unresolvedVariants = unresolvedEffectVariantIndexes(tag.variants || []);
    const unresolvedSources = unresolvedVariants.size > 0;
    const variants = tag.critical || risky
      ? formatEffectVariants(tag.name, tag, false)
      : [];
    const displayName = displayMechanicName(tag.name);
    const fallbackDetails = visibleEffectDetails(tag.name, tag.details);
    let details = "";
    if (
      tag.critical ||
      risky ||
      ["Resolve", "Super resolve", "Reduce ATK", DAMAGE_CAP_TAG].includes(tag.name)
    ) {
      details = variants.length
        ? variants.join("; ")
        : formatEffectDetails(fallbackDetails);
    }
    const badge = element(
      "span",
      classes.join(" "),
      details ? `${displayName} · ${details}` : displayName,
    );
    if (DEBUG_MODE && foundBy.length && unresolvedSources) {
      const sourceNote = foundBy.includes(primary)
        ? `Found by: ${foundBy.join(", ")}`
        : `Not in ${primary}; found by: ${foundBy.join(", ")}`;
      badge.title = details ? `${sourceNote}; Details: ${details}` : sourceNote;
    } else if (details) {
      badge.title = `Details: ${details}`;
    }
    list.append(badge);
  }
  return list;
}

function enemyAttributes(enemy) {
  const list = Array.isArray(enemy.elements)
    ? enemy.elements
    : cardElements[String(enemy.card)];
  const [main, sub] = (list || []).filter((name) => ATTRIBUTES.has(name));
  if (!main) return [];
  return sub && sub !== main ? [main, sub] : [main];
}

function renderEnemySummary(enemy) {
  const section = element("section", "enemy-summary");
  const [main, sub] = enemyAttributes(enemy);
  if (main) {
    const first = ATTRIBUTE_COLORS[main];
    const second = ATTRIBUTE_COLORS[sub || main];
    section.classList.add("has-attribute");
    section.style.borderLeft = `5px solid rgb(${second})`;
    section.style.borderRight = `5px solid rgb(${first})`;
    section.style.background =
      `linear-gradient(90deg, rgba(${second}, 0.3) 0 50%, rgba(${first}, 0.3) 50% 100%)`;
    section.title = sub
      ? `${main} above 50% HP, ${sub} at 50% HP or below`
      : main;
  }
  const heading = element("div", "enemy-heading");
  heading.append(element("h4", "", enemy.name || "Unknown enemy"));
  const stats = element("div", "enemy-stats");
  if (main) {
    stats.append(
      element("span", "enemy-attribute", sub ? `${main} → ${sub} at ≤50% HP` : main),
    );
  }
  if (enemy.card !== null && enemy.card !== undefined) {
    stats.append(element("span", "", `Card ${enemy.card}`));
  }
  if (enemy.hp !== null && enemy.hp !== undefined) {
    stats.append(element("span", "", `HP ${formatNumber(enemy.hp)}`));
  }
  if (enemy.defense !== null && enemy.defense !== undefined) {
    stats.append(element("span", "", `DEF ${formatNumber(enemy.defense)}`));
  }
  const team = teamDamage();
  if (team) {
    const halved = halvedAttributes(enemy.traits);
    const above = effectiveDamage(team, main, [], halved);
    const below = effectiveDamage(team, sub || main, [], halved);
    const text = above === below
      ? `Your damage ${formatNumber(above)}`
      : `Your damage ${formatNumber(above)} → ${formatNumber(below)} at ≤50% HP`;
    stats.append(element("span", "enemy-team-damage", text));
  }
  heading.append(stats);
  section.append(heading);

  if ((enemy.parts || []).length) {
    const parts = element("div", "enemy-parts");
    for (const part of enemy.parts) {
      parts.append(element("div", "enemy-part", `[Part] ${part.name} HP ${formatNumber(part.hp)}`));
    }
    section.append(parts);
  }
  if ((enemy.traits || []).length) {
    section.append(element("p", "enemy-traits", enemy.traits.join(" · ")));
  }
  return section;
}

function sequenceLength(actions) {
  const orders = (actions || [])
    .map((action) => action.order)
    .filter((order) => Number.isFinite(order));
  return orders.length ? Math.max(...orders) : null;
}

function sequenceTitle(group) {
  for (const enemyGroup of group.enemies || []) {
    for (const action of enemyGroup.actions || []) {
      if (action.when) return action.when;
    }
  }
  return group.title;
}

function actionQualifier(action, groupKey, sequenceTotal) {
  if (groupKey === "sequence" && Number.isFinite(action.order)) {
    return sequenceTotal
      ? `Action ${action.order} of ${sequenceTotal}`
      : `Action ${action.order}`;
  }
  if (groupKey === "normal") {
    if (action.timing_kind === "random" || action.when === "One at random") {
      return Number.isFinite(action.order)
        ? `Random option ${action.order}`
        : "One at random";
    }
    const normalAction = /^Normal action (\d+)$/.exec(action.when || "");
    if (normalAction) return `Action ${normalAction[1]}`;
  }
  return "";
}

function renderAction(action, floor, teamHp, groupKey, sequenceTotal = null, colors = new Set()) {
  const alert = alertForAction(action, floor, teamHp);
  const alertClass = alert?.startsWith("Execute")
    ? "execute"
    : alert?.startsWith("Large hit")
      ? "large"
      : "";
  const row = element(
    "div",
    `action${alert ? " hit-alert" : ""}${alertClass ? ` ${alertClass}` : ""}`,
  );
  const copy = element("div", "action-copy");
  const qualifier = actionQualifier(action, groupKey, sequenceTotal);
  if (qualifier) copy.append(element("span", "action-when", qualifier));
  const text = actionTextForGroup(action, groupKey, DEBUG_MODE);
  const risky = actionTagNames(action).some((name) =>
    affectsTeam(name, [actionDetailText(action)], colors),
  );
  if (text) {
    copy.append(element("span", `action-text${risky ? " team-risk" : ""}`, text));
  }
  if (DEBUG_MODE && action.source) {
    const source = element("span", "action-source", action.source);
    source.title = `Source: ${action.source}`;
    copy.append(source);
  }
  row.append(copy);
  if (action.hit !== null && action.hit !== undefined) {
    const normalHit = !action.already_enraged && Number.isFinite(action.normal_hit)
      ? action.normal_hit
      : action.hit;
    const enragedHit = action.already_enraged
      ? " (already enraged)"
      : Number.isFinite(action.enraged_hit)
      ? ` (enraged hit: ${formatNumber(action.enraged_hit)})`
      : "";
    const hitLabel = `${alert ? `${alert} · ` : ""}${formatNumber(normalHit)} damage${enragedHit}`;
    const chip = element(
      "span",
      `hit-chip${alert ? " alert" : ""}${alertClass ? ` ${alertClass}` : ""}`,
      hitLabel,
    );
    row.append(chip);
  }
  return row;
}

function renderTimingGroups(floor, teamHp) {
  const container = element("div", "timing-groups");
  const colors = teamColors();
  for (const enemy of floor.enemies || []) {
    const enemySection = element("section", "enemy-timing-block");
    enemySection.append(renderEnemySummary(enemy));
    for (const group of groupFloorActions({ ...floor, enemies: [enemy] })) {
      const section = element("section", "timing-group");
      const title = group.key === "sequence" ? sequenceTitle(group) : group.title;
      section.append(element("h4", "", title));
      const actions = element("div", "enemy-actions");
      for (const enemyGroup of group.enemies) {
        const total = group.key === "sequence"
          ? sequenceLength(enemyGroup.actions)
          : null;
        for (const action of enemyGroup.actions) {
          actions.append(renderAction(action, floor, teamHp, group.key, total, colors));
        }
      }
      section.append(actions);
      enemySection.append(section);
    }
    container.append(enemySection);
  }
  return container;
}

function renderFloors(data) {
  const container = document.getElementById("floors-list");
  const teamHp = selectedTeamHp();
  const primary = primarySourceName(data);
  const floors = filterFloors(data.floors || [], selectedMechanics);
  floorFilter.hidden = selectedMechanics.size === 0;
  if (selectedMechanics.size > 0) {
    const selectedLabels = [...document.querySelectorAll(".summary-mechanic")]
      .filter((button) => selectedMechanics.has(button.dataset.mechanic))
      .map((button) => button.textContent);
    floorFilterStatus.textContent = formatFilterStatus(
      floors.length,
      new Set(selectedLabels),
    );
  }
  container.replaceChildren();
  for (const floor of floors) {
    const card = element("article", "floor-card");
    const header = element("div", "floor-header");
    const title = element("h3", "", floor.label);
    if (floor.appear !== null && floor.appear !== undefined) {
      const appearance = floor.one_of
        ? `${floor.appear} of ${(floor.enemies || []).length} possible enemies appears`
        : `${floor.appear} ${floor.appear === 1 ? "appears" : "appear"}`;
      title.textContent += ` · ${appearance}`;
    }
    header.append(title);
    header.append(renderFloorTags(floor.tags, primary));
    card.append(header);
    card.append(renderTimingGroups(floor, teamHp));
    container.append(card);
  }
  if (floors.length === 0) {
    container.append(element("p", "muted", "No floors match this mechanic."));
  }
}

function renderSources(data) {
  const container = document.getElementById("source-links");
  container.replaceChildren();
  for (const source of data.sources || []) {
    const url = safeHttpUrl(source.url);
    if (url) {
      const link = element("a", "", source.name);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      container.append(link);
    } else {
      container.append(element("span", "", source.name));
    }
  }
}

function renderDungeon(rawData) {
  const data = withoutPuzzleLessonEffects(rawData);
  currentDungeon = data;
  selectedMechanics = new Set();
  document.getElementById("dungeon-title").textContent = data.name_en;
  document.getElementById("dungeon-jp").textContent = data.name_jp || "";
  document.getElementById("build-date").textContent = `Built ${data.built}`;
  renderRules(data);
  renderCriticalSummary(data);
  renderHitSummary(data);
  renderFloors(data);
  renderSources(data);
  loadStatus.hidden = true;
  errorPanel.hidden = true;
  guideContent.hidden = false;
}

async function loadDungeon(entry) {
  if (!/^[a-z0-9-]+$/.test(entry.slug)) {
    throw new Error("The selected dungeon has an invalid slug.");
  }
  const suffix = DEBUG_MODE ? "-debug" : "";
  const response = await fetch(`data/${encodeURIComponent(entry.slug)}${suffix}.json`);
  if (!response.ok) throw new Error(`Could not load data for ${entry.name_en} (${response.status}).`);
  const data = await response.json();
  if (data.slug !== entry.slug) throw new Error("The selected dungeon data does not match the index.");
  renderDungeon(data);
  updateLocation(entry.slug);
}

async function start() {
  const response = await fetch("data/index.json");
  if (!response.ok) throw new Error(`Could not load the dungeon index (${response.status}).`);
  dungeonIndex = await response.json();
  if (!Array.isArray(dungeonIndex) || dungeonIndex.length === 0) {
    throw new Error("No dungeon data is available.");
  }
  for (const entry of dungeonIndex) {
    const option = element("option", "", entry.name_en);
    option.value = entry.slug;
    dungeonSelect.append(option);
  }

  cardElements = await fetch("data/card_elements.json")
    .then((reply) => (reply.ok ? reply.json() : {}))
    .catch(() => ({}));
  const savedHp = window.localStorage.getItem(STORAGE_KEY);
  if (savedHp && Number.isFinite(Number(savedHp)) && Number(savedHp) > 0) {
    teamHpInput.value = savedHp;
  }
  const savedDamage = window.localStorage.getItem(AVERAGE_DAMAGE_KEY);
  if (savedDamage && parseDamage(savedDamage) !== null) {
    averageDamageInput.value = savedDamage;
  }
  loadTeamDamage();
  syncAverageFromTeam();
  splitClericInput.checked = window.localStorage.getItem(SPLIT_CLERIC_KEY) === "1";
  const requestedSlug = new URL(window.location.href).searchParams.get("d");
  const selected = dungeonIndex.find((entry) => entry.slug === requestedSlug) || dungeonIndex[0];
  dungeonSelect.value = selected.slug;
  await loadDungeon(selected);
}

clearFloorFilter.addEventListener("click", () => {
  selectedMechanics = new Set();
  syncMechanicControls();
  if (currentDungeon) renderFloors(currentDungeon);
});

selectAllMechanicsButton.addEventListener("click", () => {
  selectedMechanics = allMechanics(currentDungeon?.summary || {});
  syncMechanicControls();
  if (currentDungeon) renderFloors(currentDungeon);
});

dungeonSelect.addEventListener("change", async () => {
  const entry = dungeonIndex.find((item) => item.slug === dungeonSelect.value);
  if (!entry) return;
  loadStatus.hidden = false;
  loadStatus.textContent = "Loading dungeon…";
  try {
    await loadDungeon(entry);
  } catch (error) {
    showError(error instanceof Error ? error.message : "Could not load the selected dungeon.");
  }
});

teamHpInput.addEventListener("input", (event) => {
  if (teamHpInput.value.trim() === "") {
    if (event.isTrusted) window.localStorage.removeItem(STORAGE_KEY);
  } else {
    if (event.isTrusted) window.localStorage.setItem(STORAGE_KEY, teamHpInput.value);
  }
  if (currentDungeon) {
    renderHitSummary(currentDungeon);
    renderFloors(currentDungeon);
  }
});

averageDamageInput.addEventListener("input", () => {
  if (averageDamageInput.style.display === "none") return;
  const typed = averageDamageInput.value.trim();
  if (typed === "") {
    window.localStorage.removeItem(AVERAGE_DAMAGE_KEY);
  } else {
    window.localStorage.setItem(AVERAGE_DAMAGE_KEY, typed);
  }
  updateSkillPlan();
});

for (const input of teamDamageInputs.values()) {
  input.addEventListener("input", () => {
    saveTeamDamage();
    syncAverageFromTeam();
    updateSkillPlan();
    applySummaryRisks();
    if (currentDungeon) renderFloors(currentDungeon);
  });
}

splitClericInput.addEventListener("change", () => {
  if (splitClericInput.checked) {
    window.localStorage.setItem(SPLIT_CLERIC_KEY, "1");
  } else {
    window.localStorage.removeItem(SPLIT_CLERIC_KEY);
  }
  updateSkillPlan();
});

start().catch((error) => {
  showError(error instanceof Error ? error.message : "Could not load dungeon data.");
});
