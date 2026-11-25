import assert from "node:assert/strict";
import test from "node:test";

import {
  allMechanics,
  filterFloors,
  formatFilterStatus,
} from "../site/filters.mjs";

const floors = [
  { label: "Floor 1", tags: [{ name: "Damage void" }, { name: "Bind" }] },
  { label: "Floor 2", tags: [{ name: "Damage absorb" }] },
  { label: "Floor 3", tags: [] },
  { label: "Floor 4", tags: [{ name: "Unmatchable" }] },
];

test("selected mechanics use OR semantics across floors", () => {
  const selected = new Set(["Damage void", "Unmatchable"]);

  assert.deepEqual(
    filterFloors(floors, selected).map((floor) => floor.label),
    ["Floor 1", "Floor 4"],
  );
});

test("select all includes every available overview mechanic", () => {
  const summary = {
    "Damage void": ["Floor 1"],
    "Damage absorb": ["Floor 2"],
    Bind: ["Floor 1"],
    Empty: [],
  };
  const selected = allMechanics(summary);

  assert.deepEqual(
    [...selected].sort(),
    ["Bind", "Damage absorb", "Damage void"],
  );
  assert.deepEqual(
    filterFloors(floors, selected).map((floor) => floor.label),
    ["Floor 1", "Floor 2", "Floor 4"],
  );
});

test("show all floors resets the filter when no mechanics are selected", () => {
  assert.deepEqual(filterFloors(floors, new Set()), floors);
});

test("filter status lists every selected mechanic on its own line", () => {
  assert.equal(
    formatFilterStatus(14, new Set(["Damage void", "Bind"])),
    "Showing 14 floors with any of 2 selected mechanics:\n- Damage void\n- Bind",
  );
});
