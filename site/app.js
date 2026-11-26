import { allMechanics, filterFloors, formatFilterStatus } from "./filters.mjs";
import { actionTextForGroup, groupFloorActions } from "./floor-actions.mjs";

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
const DEBUG_MODE = new URL(window.location.href).searchParams.get("debug") === "1";
const DAMAGE_CAP_TAG = "Damage cap set";

let dungeonIndex = [];
let currentDungeon = null;
let selectedMechanics = new Set();

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

function selectedTeamHp() {
  const value = Number(teamHpInput.value);
  return teamHpInput.value.trim() !== "" && Number.isFinite(value) && value > 0
    ? value
    : null;
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
        floorList.append(
          element("li", "", details ? `${floorLabel} — ${details}` : `${floorLabel} — ${mechanicName}`),
        );
      }
      item.append(floorList);
      grid.append(item);
    }
    section.append(grid);
    container.append(section);
  }
  selectAllMechanicsButton.disabled = Object.keys(summary).length === 0;
  syncMechanicControls();
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
  for (const tag of tags || []) {
    const classes = ["tag"];
    if (tag.critical) classes.push("critical");
    const foundBy = tag.sources || [];
    if (!foundBy.includes(primary)) classes.push("not-primary");
    const unresolvedVariants = unresolvedEffectVariantIndexes(tag.variants || []);
    const unresolvedSources = unresolvedVariants.size > 0;
    const variants = tag.critical
      ? formatEffectVariants(tag.name, tag, false)
      : [];
    const displayName = displayMechanicName(tag.name);
    const fallbackDetails = visibleEffectDetails(tag.name, tag.details);
    let details = "";
    if (
      tag.critical ||
      ["Resolve", "Super resolve", "Your ATK down", DAMAGE_CAP_TAG].includes(tag.name)
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

function renderEnemySummary(enemy) {
  const section = element("section", "enemy-summary");
  const heading = element("div", "enemy-heading");
  heading.append(element("h4", "", enemy.name || "Unknown enemy"));
  const stats = element("div", "enemy-stats");
  if (enemy.card !== null && enemy.card !== undefined) {
    stats.append(element("span", "", `Card ${enemy.card}`));
  }
  if (enemy.hp !== null && enemy.hp !== undefined) {
    stats.append(element("span", "", `HP ${formatNumber(enemy.hp)}`));
  }
  if (enemy.defense !== null && enemy.defense !== undefined) {
    stats.append(element("span", "", `DEF ${formatNumber(enemy.defense)}`));
  }
  heading.append(stats);
  section.append(heading);

  if ((enemy.parts || []).length) {
    const parts = element("div", "enemy-parts");
    for (const part of enemy.parts) {
      parts.append(element("span", "", `${part.name} ${formatNumber(part.hp)}`));
    }
    section.append(parts);
  }
  if ((enemy.traits || []).length) {
    section.append(element("p", "enemy-traits", enemy.traits.join(" · ")));
  }
  return section;
}

function actionQualifier(action, groupKey) {
  if (groupKey === "sequence" && Number.isFinite(action.order)) {
    return `Step ${action.order}`;
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

function renderAction(action, floor, teamHp, groupKey) {
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
  const qualifier = actionQualifier(action, groupKey);
  if (qualifier) copy.append(element("span", "action-when", qualifier));
  const text = actionTextForGroup(action, groupKey, DEBUG_MODE);
  if (text) copy.append(element("span", "action-text", text));
  if (DEBUG_MODE && action.source) {
    const source = element("span", "action-source", action.source);
    source.title = `Source: ${action.source}`;
    copy.append(source);
  }
  row.append(copy);
  if (action.hit !== null && action.hit !== undefined) {
    const normalHit = Number.isFinite(action.normal_hit)
      ? action.normal_hit
      : action.hit;
    const enragedHit = Number.isFinite(action.enraged_hit)
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
  for (const enemy of floor.enemies || []) {
    const enemySection = element("section", "enemy-timing-block");
    enemySection.append(renderEnemySummary(enemy));
    for (const group of groupFloorActions({ ...floor, enemies: [enemy] })) {
      const section = element("section", "timing-group");
      section.append(element("h4", "", group.title));
      const actions = element("div", "enemy-actions");
      for (const enemyGroup of group.enemies) {
        for (const action of enemyGroup.actions) {
          actions.append(renderAction(action, floor, teamHp, group.key));
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

function renderDungeon(data) {
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

  const savedHp = window.localStorage.getItem(STORAGE_KEY);
  if (savedHp && Number.isFinite(Number(savedHp)) && Number(savedHp) > 0) {
    teamHpInput.value = savedHp;
  }
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

teamHpInput.addEventListener("input", () => {
  if (teamHpInput.value.trim() === "") {
    window.localStorage.removeItem(STORAGE_KEY);
  } else {
    window.localStorage.setItem(STORAGE_KEY, teamHpInput.value);
  }
  if (currentDungeon) {
    renderHitSummary(currentDungeon);
    renderFloors(currentDungeon);
  }
});

start().catch((error) => {
  showError(error instanceof Error ? error.message : "Could not load dungeon data.");
});