// Products page wording that depends on the numbers (lib/products-ui.ts).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  STATUS_FILTER_OPTIONS,
  auditStatusText,
  categoryColumns,
  emptyProductsText,
  lastSeenNote,
  shownConfidence,
  showStoreFilter,
  sortOptions,
} from "./products-ui.ts";

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
  assert.equal(auditStatusText("Not flagged", null), "Not reviewed");
  assert.equal(auditStatusText("Not flagged", "2026-11-26T10:00:00+07:00"), "Validated");
  assert.equal(auditStatusText("Low Confidence", null), "Low Confidence");
  assert.equal(auditStatusText("Needs Review", null), "Needs Review");
});

test("what each account sees on Category", () => {
  assert.deepEqual(categoryColumns(false, 1), { skuCode: false, confidence: false, stores: false });
  assert.deepEqual(categoryColumns(true, 1), { skuCode: true, confidence: true, stores: false });
  assert.deepEqual(categoryColumns(false, 3), { skuCode: false, confidence: false, stores: true });
  assert.equal(showStoreFilter(0), false);
  assert.equal(showStoreFilter(1), false);
  assert.equal(showStoreFilter(2), true);
  assert.deepEqual(sortOptions(false), ["On-shelf stock (high → low)", "On-shelf stock (low → high)", "Name (A → Z)"]);
  assert.equal(sortOptions(true).includes("Confidence (high → low)"), true);
  assert.deepEqual(STATUS_FILTER_OPTIONS, ["All", "Not flagged", "Needs Review", "Low Confidence"]);
});

test("an empty product list says why it is empty", () => {
  const waiting = "Products appear once your account is approved.";
  assert.equal(emptyProductsText({ approved: false, loaded: false, failed: false }), waiting);
  assert.equal(emptyProductsText({ approved: true, loaded: false, failed: false }), "Loading products…"); // not "once approved"
  assert.equal(
    emptyProductsText({ approved: true, loaded: false, failed: true }),
    "Products could not be loaded. Reload the page to try again."
  );
  assert.equal(emptyProductsText({ approved: true, loaded: true, failed: false }), "No products match the search and the filters.");
});
