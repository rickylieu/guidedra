function actionGroup(action) {
  const kind = action.timing_kind;
  const when = action.when || "Unknown timing";

  if (kind === "preemptive" || when === "Preemptive") {
    return { key: "preemptive", title: "Pre-emptive", priority: 0 };
  }
  if (kind === "first_action" || when === "First action") {
    return { key: "first_action", title: "First action", priority: 1 };
  }
  if (kind === "normal" || kind === "random" || when === "One at random" ||
      /^Normal action(?: \d+)?$/.test(when)) {
    return { key: "normal", title: "Normal action", priority: 2 };
  }
  if (kind === "sequence" || when === "Used in order") {
    return { key: "sequence", title: "In order", priority: 3 };
  }
  if (kind === "on_super_resolve" || when === "On super resolve") {
    return { key: "super_resolve", title: "On super resolve", priority: 4 };
  }
  return {
    key: `condition:${when}`,
    title: when,
    priority: 5,
  };
}

export function groupFloorActions(floor) {
  const groups = new Map();
  let firstSeen = 0;

  for (const [enemyIndex, enemy] of (floor.enemies || []).entries()) {
    for (const [actionIndex, action] of (enemy.actions || []).entries()) {
      const descriptor = actionGroup(action);
      let group = groups.get(descriptor.key);
      if (!group) {
        group = { ...descriptor, firstSeen: firstSeen++, enemies: new Map() };
        groups.set(descriptor.key, group);
      }

      let enemyGroup = group.enemies.get(enemyIndex);
      if (!enemyGroup) {
        enemyGroup = { enemy, actions: [] };
        group.enemies.set(enemyIndex, enemyGroup);
      }
      enemyGroup.actions.push({ action, actionIndex });
    }
  }

  return [...groups.values()]
    .sort((left, right) =>
      left.priority - right.priority || left.firstSeen - right.firstSeen)
    .map((group) => ({
      key: group.key,
      title: group.title,
      enemies: [...group.enemies.values()].map(({ enemy, actions }) => ({
        enemy,
        actions: actions
          .sort((left, right) => {
            if (group.key !== "sequence") return left.actionIndex - right.actionIndex;
            const leftOrder = Number.isFinite(left.action.order)
              ? left.action.order
              : Number.MAX_SAFE_INTEGER;
            const rightOrder = Number.isFinite(right.action.order)
              ? right.action.order
              : Number.MAX_SAFE_INTEGER;
            return leftOrder - rightOrder || left.actionIndex - right.actionIndex;
          })
          .map(({ action }) => action),
      })),
    }));
}

export function actionTextForGroup(action, groupKey, debug = false) {
  const text = action.text || (
    debug && action.untranslated_text_jp
      ? `No English annotation (${action.untranslated_text_jp})`
      : "No English annotation"
  );
  if (groupKey !== "preemptive") return text;
  return text
    .replace(/\bPreemptive\b/g, "")
    .replace(/\s*,\s*,\s*/g, ", ")
    .replace(/,\s*(?=\()/g, " ")
    .replace(/^\s*,\s*|\s*,\s*$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
