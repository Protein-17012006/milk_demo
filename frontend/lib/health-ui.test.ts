// Unit tests for the Model page's Live health chart (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { ApiModelHealthItem } from "./api";
import { formatHealth, healthChart, latestHealth } from "./health-ui.ts";

/** One camera-hour as GET /model/health returns it; fields the test does not set are absent, as for an hour with no box. */
function hour(camera_id: string, h: string, fields: Partial<ApiModelHealthItem> = {}): ApiModelHealthItem {
  return { camera_id, hour: h, captures: 1, ...fields };
}

test("hours without captures stay empty, so the line breaks there instead of joining far-apart hours", () => {
  const chart = healthChart(
    [hour("CAM-A", "20261122-23", { conf_median: 0.37 }), hour("CAM-A", "20261123-01", { conf_median: 0.77 })],
    "conf_median"
  );
  assert.deepEqual(chart.cameras, ["CAM-A"]);
  assert.deepEqual(chart.rows, [
    { hour: "20261122-23", label: "22/11 23h", "CAM-A": 0.37 },
    { hour: "20261123-00", label: "23/11 00h", "CAM-A": null },
    { hour: "20261123-01", label: "23/11 01h", "CAM-A": 0.77 },
  ]);
});

test("a share is drawn as a percentage", () => {
  const chart = healthChart([hour("CAM-A", "20261123-12", { flagged_row_pct: 0.25 })], "flagged_row_pct");
  assert.equal(chart.rows[0]["CAM-A"], 25);
});

test("each camera gets its own line", () => {
  const chart = healthChart(
    [
      hour("CAM-B", "20261123-10", { captures: 5 }),
      hour("CAM-A", "20261123-10", { captures: 7 }),
      hour("CAM-B", "20261123-11", { captures: 9 }),
    ],
    "captures"
  );
  assert.deepEqual(chart.cameras, ["CAM-A", "CAM-B"]);
  assert.deepEqual(chart.rows, [
    { hour: "20261123-10", label: "23/11 10h", "CAM-A": 7, "CAM-B": 5 },
    { hour: "20261123-11", label: "23/11 11h", "CAM-A": null, "CAM-B": 9 },
  ]);
});

test("no health items give an empty chart", () => {
  assert.deepEqual(healthChart([], "conf_median"), { cameras: [], rows: [] });
});

test("the latest value comes from the last hour that has one", () => {
  // conf_median is absent in an hour whose captures found no box
  const items = [hour("CAM-A", "20261123-21", { conf_median: 0.33 }), hour("CAM-A", "20261123-22")];
  assert.deepEqual(latestHealth(items, "conf_median"), [
    { camera: "CAM-A", hour: "20261123-21", label: "23/11 21h", value: 0.33 },
  ]);
});

test("the latest share is a percentage too", () => {
  assert.deepEqual(latestHealth([hour("CAM-A", "20261123-22", { flagged_row_pct: 0.5 })], "flagged_row_pct"), [
    { camera: "CAM-A", hour: "20261123-22", label: "23/11 22h", value: 50 },
  ]);
});

test("values are shown with their units", () => {
  assert.equal(formatHealth("conf_median", 0.1666), "0.17");
  assert.equal(formatHealth("flagged_row_pct", 96.4), "96%");
  assert.equal(formatHealth("jitter", 1.62), "1.6 units");
  assert.equal(formatHealth("processing_ms_median", 188.6), "189 ms");
  assert.equal(formatHealth("captures", 63), "63");
  assert.equal(formatHealth("conf_median", null), "—");
});
