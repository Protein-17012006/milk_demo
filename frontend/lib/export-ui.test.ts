import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultExportRange, earliestExportDay, exportDoneText, exportRangeError, ictDay } from "./export-ui.ts";

const NOW = new Date("2026-11-26T13:40:00Z"); // 20:40 on 26/11 in UTC+7

test("the day is the UTC+7 day", () => {
  assert.equal(ictDay(NOW), "2026-11-26");
  assert.equal(ictDay(new Date("2026-11-26T17:30:00Z")), "2026-11-27"); // 00:30 the next day in UTC+7
  assert.deepEqual(defaultExportRange(NOW), { from: "2026-11-26", to: "2026-11-26" });
  assert.equal(earliestExportDay(NOW), "2026-11-20");
});

test("a range is checked before anything is sent", () => {
  assert.equal(exportRangeError({ from: "2026-11-20", to: "2026-11-26" }, NOW), null);
  assert.equal(exportRangeError({ from: "2026-11-26", to: "2026-11-26" }, NOW), null);
  assert.equal(exportRangeError({ from: "", to: "2026-11-26" }, NOW), "Choose the first and the last day.");
  assert.equal(exportRangeError({ from: "2026-11-26", to: "2026-11-25" }, NOW), "The first day is after the last day.");
  assert.equal(exportRangeError({ from: "2026-11-26", to: "2026-11-27" }, NOW), "The last day is in the future.");
  assert.equal(
    exportRangeError({ from: "2026-11-19", to: "2026-11-26" }, NOW),
    "Captures are kept for 7 days. Choose days from 20/11 on."
  );
});

test("the closing line says what was downloaded", () => {
  assert.equal(exportDoneText(9819, { from: "2026-11-24", to: "2026-11-26" }), "Downloaded 9,819 rows for 24/11 to 26/11.");
  assert.equal(exportDoneText(1, { from: "2026-11-26", to: "2026-11-26" }), "Downloaded 1 row for 26/11.");
  assert.equal(
    exportDoneText(0, { from: "2026-11-26", to: "2026-11-26" }),
    "No captures on 26/11: the file has only the header row."
  );
  assert.equal(
    exportDoneText(0, { from: "2026-11-24", to: "2026-11-26" }),
    "No captures from 24/11 to 26/11: the file has only the header row."
  );
});
