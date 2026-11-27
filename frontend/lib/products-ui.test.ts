// Products page wording that depends on the numbers (lib/products-ui.ts).
import assert from "node:assert/strict";
import { test } from "node:test";

import { auditStatusText, lastSeenNote, shownConfidence } from "./products-ui.ts";

test("a row without units shows no confidence: the score is of an older reading", () => {
  assert.equal(shownConfidence(0, 0.9), null);
  assert.equal(shownConfidence(6, 0.95), 0.95);
});

test("a card at 0 units says its frame and boxes are from the last sighting", () => {
  assert.equal(
    lastSeenNote(0, 8, "2026-11-26T15:40:28+07:00"),
    "Not on the shelf at the last check. The frame and its 8 boxes are from 15:40 on 26/11, when it was last seen.",
  );
  assert.equal(
    lastSeenNote(0, 1, "2026-11-26T15:40:28+07:00"),
    "Not on the shelf at the last check. The frame and its 1 box are from 15:40 on 26/11, when it was last seen.",
  );
});

test("a card with units, or one that never had a box, needs no such note", () => {
  assert.equal(lastSeenNote(6, 6, "2026-11-26T15:45:23+07:00"), null);
  assert.equal(lastSeenNote(0, 0, null), null);
});

test("only a reading a person reviewed is called validated", () => {
  assert.equal(auditStatusText("Validated", null), "Not reviewed");
  assert.equal(auditStatusText("Validated", "2026-11-26T10:00:00+07:00"), "Validated");
  assert.equal(auditStatusText("Low Confidence", null), "Low Confidence");
  assert.equal(auditStatusText("Needs Review", null), "Needs Review");
});
