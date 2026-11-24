// Unit tests for the Dashboard's shelf text helpers (run: npm test). Expected strings follow the Figma card.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { ApiShelfEvent } from "./api";
import { blockedText, dashboardQuery, eventLabel, eventText, oosDurationText, pctChange, ptsChange, timeAgo } from "./shelf-ui.ts";

function ev(type: ApiShelfEvent["type"], delta: number, levelAfter: number): ApiShelfEvent {
  return {
    event_key: `20261124-0950#Slide Cheese 145g#${type}`,
    store_id: "DEMO-S01",
    store_name: "Demo Store S01",
    sku_id: "Slide Cheese 145g",
    sku_name: "Slide Cheese 145g",
    type,
    at: "20261124-0950",
    delta,
    level_before: levelAfter - delta,
    level_after: levelAfter,
    duration_min: null,
  };
}

test("events read as on the Figma card", () => {
  assert.equal(eventText(ev("OOS", -6, 0)), "0 units (−6)");
  assert.equal(eventText(ev("RESTOCKED", 16, 24)), "+16 units (24 total)");
  assert.equal(eventText(ev("DEPLETED", -4, 8)), "−4 units (8 left)");
  assert.equal(eventText(ev("LOW_STOCK", -6, 2)), "2 left (−6)");
  assert.equal(eventLabel("LOW_STOCK"), "LOW STOCK");
});

test("time ago from a 5-minute bucket", () => {
  const now = new Date("2026-11-24T10:00:00+07:00");
  assert.equal(timeAgo("20261124-0950", now), "10 min ago");
  assert.equal(timeAgo("20261124-0900", now), "1 hr ago");
  assert.equal(timeAgo("20261123-1000", now), "1 day ago");
  assert.equal(timeAgo("20261122-1000", now), "2 days ago");
});

test("changes against the previous period", () => {
  assert.equal(ptsChange(0.66, 0.62), "+4.0 pts");
  assert.equal(ptsChange(0.62, 0.66), "−4.0 pts");
  assert.equal(ptsChange(0.6, null), null);
  assert.equal(pctChange(34), "+34%");
  assert.equal(pctChange(-12.5), "−12.5%");
  assert.equal(pctChange(null), null);
});

test("a blocked card says what to do", () => {
  assert.equal(blockedText("no_hours", "DEMO-S01"), "Set opening hours for DEMO-S01 in Settings");
  assert.equal(blockedText("no_labels"), "Label frames on the Model page");
  assert.equal(blockedText("no_previous"), "Needs the previous period's data to compare");
});

test("dashboard filters become the API query, leaving out what is not set", () => {
  assert.equal(
    dashboardQuery({ days: 14, storeId: "DEMO-S01", category: "Milk", kind: "alerts" }),
    "?days=14&store_id=DEMO-S01&category=Milk&kind=alerts"
  );
  assert.equal(dashboardQuery({ days: 7 }), "?days=7");
  assert.equal(dashboardQuery({}), "");
});

test("oosDurationText: only a RESTOCKED that ended an out-of-stock says how long; a missing field says nothing", () => {
  assert.equal(oosDurationText({ duration_min: 80 }), " · out of stock 80 min");
  assert.equal(oosDurationText({ duration_min: null }), "");
  // DynamoDB drops empty fields, so OOS events reach the page without duration_min at all
  assert.equal(oosDurationText({} as { duration_min?: number | null }), "");
});
