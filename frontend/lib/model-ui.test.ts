// Unit tests for how the Model page shows Datagent's KPIs (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  cellText,
  checkLevelText,
  ciText,
  displayCheckText,
  kpiCiText,
  kpiDisplay,
  myLabelsText,
  notEnoughText,
  periodCellText,
  signedText,
  statParts,
  statText,
} from "./model-ui.ts";

test("a share is shown as a percentage beside its target", () => {
  assert.deepEqual(
    kpiDisplay("overall_identification_accuracy", { value: 0.5, target: [">=", 0.6], met: false, n: 4 }),
    { text: "50.0%", targetText: "≥ 60%", tone: "missed" }
  );
});

test("a KPI without samples shows a dash, never zero", () => {
  assert.deepEqual(
    kpiDisplay("unit_count_mae", { value: null, target: ["<=", 2], met: null, n: 0 }),
    { text: "—", targetText: "≤ 2", tone: "none" }
  );
});

test("counts, confidences and times keep their own units", () => {
  assert.equal(kpiDisplay("unit_count_mae", { value: 0.6667, target: ["<=", 2], met: true, n: 3 }).text, "0.67");
  assert.equal(kpiDisplay("avg_confidence_incorrect", { value: 0.8867, target: ["<", 0.5], met: false, n: 3 }).text, "0.89");
  assert.deepEqual(
    kpiDisplay("avg_processing_time_ms", { value: 54.4, target: ["<=", 30000], met: true, n: 900 }),
    { text: "54 ms", targetText: "≤ 30000 ms", tone: "met" }
  );
});

test("a 95% interval is shown in the unit of its number, and not at all without one", () => {
  assert.equal(ciText([0.75, 0.83]), "(75–83%)");
  assert.equal(ciText([0.5, 0.8333], "number"), "(0.50–0.83)");
  assert.equal(ciText([-3, 1], "signed"), "(−3.0 to +1.0)");
  assert.equal(ciText(null), "");
  assert.equal(ciText(undefined), "");
});

test("a KPI's interval follows the KPI's unit", () => {
  assert.equal(kpiCiText("overall_identification_accuracy", [0.5, 0.625]), "(50–63%)");
  assert.equal(kpiCiText("unit_count_mae", [0.6667, 2]), "(0.67–2.00)");
  assert.equal(kpiCiText("avg_processing_time_ms", undefined), "");
});

test("a signed mean keeps the site's minus sign and drops the sign at zero", () => {
  assert.deepEqual([signedText(-2), signedText(0.6667), signedText(-0.04)], ["−2.0", "+0.7", "0.0"]);
});

test("a table number with nothing to divide by says its n, never a bare dash or 0%", () => {
  assert.equal(cellText(null, "percent", 0, "box", "boxes"), "Not enough samples (n = 0 boxes)"); // never named
  assert.equal(cellText(null, "percent", 0, "can"), "Not enough samples (n = 0 cans)"); // never really there
  assert.equal(cellText(null, "signed", 0, "frame"), "Not enough samples (n = 0 frames)");
  assert.equal(cellText(0.775, "percent", 40, "box", "boxes"), "77.5%");
  assert.equal(cellText(-1.5, "signed", 11, "frame"), "−1.5");
  assert.equal(cellText(undefined, "percent", 34, "can"), "—"); // an older backend does not send the number at all
});

test("a ratio with its interval and n, or not enough samples instead of 0%", () => {
  const agree = { value: 0.787, ci: [0.75, 0.83] as [number, number], n: 11 };
  assert.equal(statText(agree, "percent", "frame"), "78.7% (75–83%, n = 11 frames)");
  assert.equal(statText({ value: 0.5, ci: null, n: 1 }, "percent", "frame"), "50.0% (n = 1 frame)");
  assert.equal(statText({ value: null, ci: null, n: 0 }, "percent", "SKU row"), "Not enough samples (n = 0 SKU rows)");
  assert.equal(statText({ value: 0.625, ci: null, n: 8 }, "percent", "box", "boxes"), "62.5% (n = 8 boxes)");
  assert.deepEqual(statParts({ value: null, ci: null, n: 0 }), { text: "Not enough samples", detail: "(n = 0)" });
});

test("a SKU below the sample rule says which part is short", () => {
  assert.equal(notEnoughText({ frames: 1, true_units: 3, days: 1 }), "Not enough samples (n = 1 frame · 3 cans · 1 day)");
  assert.equal(notEnoughText({ frames: 0, true_units: 0, days: 0 }), "Not enough samples (n = 0 frames)");
  assert.equal(notEnoughText({ true_units: 0 }), "Not enough samples (n = 0 frames)"); // older backends: no frames
});

test("a time-of-day cell gives both ways, or why it cannot", () => {
  const cell = { named_right: 0.9, found_right: 0.8, model_units: 30, true_units: 34, frames: 12, days: 3, enough: true };
  assert.equal(periodCellText(cell), "found right 80.0% · named right 90.0%");
  assert.equal(
    periodCellText({ ...cell, named_right: null, model_units: 0 }), // true cans the model never named
    "found right 80.0% · named right Not enough samples (n = 0 boxes)"
  );
  assert.equal(periodCellText({ ...cell, frames: 4, enough: false }), "Not enough samples (n = 4 frames · 34 cans · 3 days)");
  assert.equal(periodCellText(undefined), "Not enough samples (n = 0 frames)"); // not seen at that time of day
});

test("the Dashboard checks line gives the signed count error and present-or-absent agreement", () => {
  const stat = (value: number | null, n: number, ci: [number, number] | null = null) => ({ value, ci, n });
  assert.equal(
    checkLevelText({ frames: 2, count_mae: stat(1.3333, 6), count_bias: stat(-0.6667, 6, [-1, -0.3333]), presence_agree: stat(0.875, 8, [0.75, 1]) }),
    "Dashboard checks (2 frames): cans per SKU off by −0.7 (−1.0 to −0.3, n = 6 SKU rows) · " +
      "present or absent agree 87.5% (75–100%, n = 8 SKU rows)"
  );
  assert.equal(
    checkLevelText({ frames: 0, count_mae: stat(null, 0), count_bias: stat(null, 0), presence_agree: stat(null, 0) }),
    "Dashboard checks: Not enough samples (n = 0 frames)"
  );
});

test("the display check line counts both ways it can be wrong", () => {
  assert.equal(
    displayCheckText({ agree: { value: 2 / 3, ci: [0.3333, 1], n: 3 }, false_not_visible: 1, false_visible: 0 }),
    'Display check: matched the labellers on 66.7% (33–100%, n = 3 scoring frames) · wrongly "not in view" 1 · ' +
      'wrongly "in view" 0'
  );
  assert.equal(
    displayCheckText({ agree: { value: null, ci: null, n: 0 }, false_not_visible: 0, false_visible: 0 }),
    "Display check: Not enough samples (n = 0 scoring frames)"
  );
});

test("under 10 frames judged by the check, the display check gives its n instead of a share", () => {
  // GET /model/summary sends a null share and the n of judged frames below 10; the wrong counts wait for a share
  assert.equal(
    displayCheckText({ agree: { value: null, ci: null, n: 7 }, false_not_visible: 1, false_visible: 0 }),
    "Display check: Not enough samples (n = 7 scoring frames)"
  );
});

// --- "Your labels": what the signed-in labeller did and where it is (operations-loop design 5.4) ---

const NO_LABELS = { frames: 0, boxes: 0, missed: 0 };

test("my labels: nothing yet", () => {
  assert.deepEqual(myLabelsText({ teaching: NO_LABELS, scoring: NO_LABELS, in_live_version: null }), [
    "You have not labelled a frame yet.",
  ]);
});

test("my labels: no live version was trained with labels, said plainly", () => {
  assert.deepEqual(
    myLabelsText({
      teaching: { frames: 43, boxes: 618, missed: 180 },
      scoring: { frames: 70, boxes: 774, missed: 47 },
      in_live_version: null,
    }),
    [
      "Your labels on training frames: 618 boxes and 180 missed units on 43 frames. No live version has been trained from people's labels yet, so they wait for the first training; no date is set.",
      "Scoring frames you labelled: 70. They measure the model on this page and are never used to train it.",
    ]
  );
});

test("my labels: one of each reads in the singular", () => {
  const lines = myLabelsText({
    teaching: { frames: 1, boxes: 1, missed: 1 },
    scoring: NO_LABELS,
    in_live_version: null,
  });
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^Your labels on training frames: 1 box and 1 missed unit on 1 frame\. /);
});

test("my labels: a live version was trained with labels", () => {
  const lines = myLabelsText({
    teaching: { frames: 43, boxes: 618, missed: 180 },
    scoring: NO_LABELS,
    in_live_version: { version_id: "slide-v4", live_since: "2026-12-10T09:00:00+07:00", label_frames: 60 },
  });
  assert.deepEqual(lines, [
    "Your labels on training frames: 618 boxes and 180 missed units on 43 frames. Version slide-v4, live since 10/12, was trained with 60 labelled frames.",
  ]);
});

test("my labels: only scoring frames so far", () => {
  assert.deepEqual(
    myLabelsText({ teaching: NO_LABELS, scoring: { frames: 2, boxes: 20, missed: 0 }, in_live_version: null }),
    [
      "You have not labelled a training frame yet.",
      "Scoring frames you labelled: 2. They measure the model on this page and are never used to train it.",
    ]
  );
});
