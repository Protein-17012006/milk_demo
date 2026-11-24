// Unit tests for how the trend chart draws its points (run: npm test).
import { test } from "node:test";
import assert from "node:assert/strict";
import { trendRows } from "./trend-rows.ts";

test("a point without a value stays null, never 0, so the chart leaves a gap", () => {
  const rows = trendRows(
    [
      { t: "2026-11-26", value: 4 },
      { t: "2026-11-27", value: null },
      { t: "2026-11-28", value: 0 },
    ],
    "units"
  );
  assert.deepEqual(
    rows.map((r) => r.value),
    [4, null, 0]
  );
});

test("a percent value is scaled to one decimal and labels follow the point", () => {
  const rows = trendRows(
    [
      { t: "2026-11-27", value: 0.6437 },
      { t: "20261128-09", value: null },
    ],
    "%"
  );
  assert.deepEqual(rows, [
    { label: "27/11", value: 64.4 },
    { label: "09h", value: null },
  ]);
});
