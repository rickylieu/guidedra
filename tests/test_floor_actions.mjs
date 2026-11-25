import assert from "node:assert/strict";
import test from "node:test";

import { actionTextForGroup, groupFloorActions } from "../site/floor-actions.mjs";

test("groups floor actions by ordered timing and combines normal with random", () => {
  const floor = {
    enemies: [
      {
        name: "First enemy",
        actions: [
          { when: "Below 50% HP", timing_kind: "hp_threshold", text: "Threshold action" },
          { when: "Normal action 2", timing_kind: "normal", order: 2, text: "Normal action" },
          { when: "Preemptive", timing_kind: "preemptive", text: "Preemptive action" },
          { when: "Used in order", timing_kind: "sequence", order: 2, text: "Step two" },
          { when: "One at random", timing_kind: "random", order: 1, text: "Random option" },
          { when: "First action", timing_kind: "first_action", text: "Opening action" },
          { when: "On super resolve", timing_kind: "on_super_resolve", text: "Resolve action" },
          { when: "Used in order", timing_kind: "sequence", order: 1, text: "Step one" },
        ],
      },
      {
        name: "Second enemy",
        actions: [
          { when: "Preemptive", timing_kind: "preemptive", text: "Second preemptive" },
          { when: "One at random", timing_kind: "random", order: 2, text: "Another option" },
        ],
      },
    ],
  };

  const groups = groupFloorActions(floor);
  assert.deepEqual(groups.map(({ key }) => key), [
    "preemptive",
    "first_action",
    "normal",
    "sequence",
    "super_resolve",
    "condition:Below 50% HP",
  ]);
  assert.equal(groups[0].title, "Pre-emptive");
  assert.equal(groups[0].enemies.length, 2);
  assert.deepEqual(
    groups.find(({ key }) => key === "normal").enemies.flatMap(({ actions }) =>
      actions.map(({ text }) => text)),
    ["Normal action", "Random option", "Another option"],
  );
  assert.deepEqual(
    groups.find(({ key }) => key === "sequence").enemies[0].actions.map(
      ({ text }) => text,
    ),
    ["Step one", "Step two"],
  );
});

test("omits redundant preemptive wording while preserving other action details", () => {
  assert.equal(
    actionTextForGroup(
      { text: "Status immunity, Preemptive (for 10 turns)" },
      "preemptive",
    ),
    "Status immunity (for 10 turns)",
  );
  assert.equal(
    actionTextForGroup({ text: "Preemptive" }, "preemptive"),
    "",
  );
  assert.equal(
    actionTextForGroup({ text: "Preemptive (for 1 turn)" }, "condition:Below 50% HP"),
    "Preemptive (for 1 turn)",
  );
  assert.equal(
    actionTextForGroup(
      { untranslated_text_jp: "未注釈の行動" },
      "normal",
      true,
    ),
    "No English annotation (未注釈の行動)",
  );
  assert.equal(
    actionTextForGroup(
      { untranslated_text_jp: "未注釈の行動" },
      "normal",
      false,
    ),
    "No English annotation",
  );
});
