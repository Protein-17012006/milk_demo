// Unit tests for the reliability badge text (run: npm test). The badge itself is worked out by the backend.
import { test } from "node:test";
import assert from "node:assert/strict";
import { badgeLabel, badgePillText, reliabilityText } from "./reliability-ui.ts";
import type { ApiReliability } from "./api";

function rel(over: Partial<ApiReliability>): ApiReliability {
  return {
    badge: "low",
    named_right: 0.5,
    found_right: 0.24,
    true_units: 21,
    frames: 9,
    confused_as: "Slide Cheese 145g",
    ...over,
  };
}

test("badge labels", () => {
  assert.equal(badgeLabel("high"), "High");
  assert.equal(badgeLabel("medium"), "Medium");
  assert.equal(badgeLabel("low"), "Low");
  assert.equal(badgeLabel("insufficient"), "Not enough samples");
});

test("the details say what was found right, how many cans and frames, and what it is often read as", () => {
  assert.equal(reliabilityText(rel({})), "found right 24% · 21 cans · 9 frames · often read as Slide Cheese 145g");
});

test("nothing is said of a confusion that is not there, and singular counts read singular", () => {
  assert.equal(reliabilityText(rel({ confused_as: null, true_units: 1, frames: 1 })), "found right 24% · 1 can · 1 frame");
});

test("not enough samples gives the counts and no percent", () => {
  assert.equal(
    reliabilityText(rel({ badge: "insufficient", found_right: 0.9, true_units: 8, frames: 3 })),
    "Not enough samples (n = 8 cans, 3 frames)"
  );
  assert.equal(
    reliabilityText(rel({ badge: "insufficient", found_right: null, true_units: 0, frames: 0, confused_as: null })),
    "Not enough samples (n = 0 cans, 0 frames)"
  );
});

test("a SKU with no true cans to find shows no percent either", () => {
  assert.equal(reliabilityText(rel({ found_right: null })), "21 cans · 9 frames · often read as Slide Cheese 145g");
});

test("a pill with no column header above it says what it rates", () => {
  assert.equal(badgePillText("high"), "Reliability: High");
  assert.equal(badgePillText("low"), "Reliability: Low");
  assert.equal(badgePillText("insufficient"), "Reliability: not rated"); // short: the row has ~150 px for it
});
