export function allMechanics(summary) {
  return new Set(
    Object.entries(summary || {})
      .filter(([, floors]) => Array.isArray(floors) && floors.length > 0)
      .map(([mechanic]) => mechanic),
  );
}

export function filterFloors(floors, selectedMechanics) {
  if (selectedMechanics.size === 0) return floors;
  return floors.filter((floor) =>
    floor.tags?.some((tag) => selectedMechanics.has(tag.name)),
  );
}

export function formatFilterStatus(floorCount, selectedMechanics) {
  const floorWord = floorCount === 1 ? "floor" : "floors";
  const mechanics = [...selectedMechanics].map((name) => `- ${name}`).join("\n");
  return `Showing ${floorCount} ${floorWord} with any of ${selectedMechanics.size} selected mechanics:\n${mechanics}`;
}
