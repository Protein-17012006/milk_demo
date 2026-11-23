// Unit tests for how the Model page shows Datagent's KPIs (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import { kpiDisplay } from "./model-ui.ts";

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
