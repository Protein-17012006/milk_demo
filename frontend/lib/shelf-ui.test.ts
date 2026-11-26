// Unit tests for the Dashboard's shelf text helpers (run: npm test). Expected strings follow the Figma card.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { ApiShelfEvent } from "./api";
import { alertAccuracyByTypeText, alertAccuracyText, blockedText, coverageText, dashboardQuery, displayBanner, gapText, eventLabel, eventText, oosDurationText, pctChange, ptsChange, timeAgo,
  restockDefinition,
} from "./shelf-ui.ts";

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

test("an event after a gap says when the shelf was not seen", () => {
  assert.equal(
    gapText({ after_gap: true, gap_from: "20261123-2025", gap_to: "20261124-0845" }),
    "between 20:30 and 08:45 (not measured)"
  );
  assert.equal(gapText({}), null);
  assert.equal(gapText({ after_gap: true }), null); // no buckets: say nothing rather than guess
});

test("coverage text", () => {
  assert.equal(
    coverageText({ measured_hours: 9.5, open_hours: 12.5, display_away_hours: 1 }),
    "Measured 9.5 h of 12.5 h open · display not in view 1 h"
  );
  assert.equal(
    coverageText({ measured_hours: 12.5, open_hours: 12.5, display_away_hours: 0 }),
    "Measured 12.5 h of 12.5 h open"
  );
});

test("a banner for each camera that cannot see the display", () => {
  assert.equal(
    displayBanner([{ camera_id: "CAM-S01-A", store_id: "DEMO-S01", visible: false, since: "2026-11-23T20:45:10+07:00", last_visible_at: "2026-11-23T20:40:05+07:00" }]),
    "CAM-S01-A cannot see the display since 20:45 — numbers below are from the last check at 20:40"
  );
  assert.equal(displayBanner([]), null);
  assert.equal(
    displayBanner([{ camera_id: "CAM-S01-A", store_id: "DEMO-S01", visible: true, since: "2026-11-23T20:45:10+07:00", last_visible_at: "2026-11-23T20:45:10+07:00" }]),
    null
  );
});

test("the banner never says it cannot see since before the last time it saw", () => {
  // captures out of order: since 14:10 but last seen 14:12
  assert.equal(
    displayBanner([{ camera_id: "CAM-S01-A", store_id: "DEMO-S01", visible: false, since: "2026-11-21T14:10:00+07:00", last_visible_at: "2026-11-21T14:12:00+07:00" }]),
    "CAM-S01-A cannot see the display since 14:12 — numbers below are from the last check at 14:12"
  );
});

test("several cameras that cannot see the display get a line each", () => {
  const a = { store_id: "DEMO-S01", visible: false, since: "2026-11-23T20:45:00+07:00", last_visible_at: "2026-11-23T20:40:00+07:00" };
  assert.equal(
    displayBanner([{ camera_id: "A", ...a }, { camera_id: "B", ...a }]),
    "A cannot see the display since 20:45 — numbers below are from the last check at 20:40\nB cannot see the display since 20:45 — numbers below are from the last check at 20:40"
  );
});

test("a camera that never saw the display has no last check to point to", () => {
  assert.equal(
    displayBanner([{ camera_id: "A", store_id: "DEMO-S01", visible: false, since: "2026-11-23T20:45:00+07:00", last_visible_at: null }]),
    "A cannot see the display since 20:45 — there is no earlier check to show"
  );
});

test("alert accuracy says how many were right, and the unsure ones apart", () => {
  assert.equal(
    alertAccuracyText({ value: 0.7, n: 10, unsure: 1, blocked_reason: null }),
    "Alerts confirmed right: 7 of 10 (1 unsure)"
  );
  assert.equal(alertAccuracyText({ value: 0.8, n: 10, unsure: 0, blocked_reason: null }), "Alerts confirmed right: 8 of 10");
});

test("alert accuracy below 10 says not enough samples, and asks only those who can confirm", () => {
  const blocked = { value: null, blocked_reason: "few_verified" as const, n: 3, unsure: 0 };
  assert.equal(alertAccuracyText(blocked, true), "Too few confirmed alerts to rate them (3 so far) · confirm 7 more alerts to see how often they are right");
  assert.equal(alertAccuracyText(blocked, false), "Too few confirmed alerts to rate them (3 so far)");
  assert.equal(alertAccuracyText(blocked), "Too few confirmed alerts to rate them (3 so far)");
  assert.equal(
    alertAccuracyText({ value: null, blocked_reason: "few_verified", n: 9, unsure: 2 }, true),
    "Too few confirmed alerts to rate them (9 so far) · confirm 1 more alert to see how often they are right (2 unsure)"
  );
  assert.equal(alertAccuracyText(undefined), null);
});

test("alert accuracy per kind of event leaves out kinds nobody confirmed", () => {
  assert.equal(
    alertAccuracyByTypeText({
      RESTOCKED: { right: 3, wrong: 1, unsure: 0 },
      OOS: { right: 7, wrong: 2, unsure: 1 },
      DEPLETED: { right: 0, wrong: 0, unsure: 2 },
    }),
    "OOS 7 of 9 · Restocked 3 of 4"
  );
  assert.equal(alertAccuracyByTypeText({}), null);
  assert.equal(alertAccuracyByTypeText(undefined), null);
});

test("the restock card says over how many days with checks its rate is", () => {
  assert.equal(
    restockDefinition(14, 5),
    "Units restocked per day that has checks (5 of the last 14 days), against the 14 days before.",
  );
  assert.equal(restockDefinition(1, 1), "Units restocked today, against yesterday.");
  assert.equal(restockDefinition(14, undefined), "Units restocked per day, against the 14 days before.");
});
