// Unit tests for the Products review queue summary (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  cardFromQueueItem,
  correctionChanged,
  correctionToast,
  orderForReview,
  queueKeyForReading,
  reviewSummary,
} from "./review-queue.ts";

const item = (status: string, flag_reason: string, capture_timestamp = "2026-11-23T22:00:00+07:00", queue_key = "k") => ({
  status,
  flag_reason,
  capture_timestamp,
  queue_key,
});

test("only readings nobody has confirmed or corrected are waiting, counted by reason", () => {
  const summary = reviewSummary([
    item("Chờ duyệt", "Low Confidence"),
    item("Chờ duyệt", "Unrecognized"),
    item("Chờ duyệt", "Low Confidence"),
    item("Đã xác nhận", "Low Confidence"),
    item("Đã sửa", "Unrecognized"),
  ]);
  assert.deepEqual(summary, { waiting: 3, waitingLowConfidence: 2, waitingUnrecognized: 1, checked: 2 });
});

test("an empty queue has nothing waiting", () => {
  assert.deepEqual(reviewSummary([]), { waiting: 0, waitingLowConfidence: 0, waitingUnrecognized: 0, checked: 0 });
});

test("a status the page does not know is still waiting, never counted as checked", () => {
  assert.deepEqual(reviewSummary([item("", "Low Confidence")]), {
    waiting: 1,
    waitingLowConfidence: 1,
    waitingUnrecognized: 0,
    checked: 0,
  });
});

test("waiting items come first, newest first within each group", () => {
  const ordered = orderForReview([
    item("Đã xác nhận", "Low Confidence", "2026-11-23T22:00:00+07:00", "a"),
    item("Chờ duyệt", "Low Confidence", "2026-11-23T20:00:00+07:00", "b"),
    item("Chờ duyệt", "Unrecognized", "2026-11-23T21:00:00+07:00", "c"),
    item("Đã sửa", "Low Confidence", "2026-11-23T23:00:00+07:00", "d"),
  ]);
  assert.deepEqual(
    ordered.map((i) => i.queue_key),
    ["c", "b", "d", "a"]
  );
});

// --- 2026-11-26: one review flow. "Correct" opens the card on the flagged reading; saving checks the item off ---

const flagged = (over: Record<string, unknown> = {}) =>
  ({
    store_id: "DEMO-S01",
    queue_key: "CAM-S01-A#Slide Sour Cream & Onion 150g#Low Confidence",
    reading_id: "RD-S01-20261125-183012-002",
    capture_id: "CAP-S01-20261125-183012",
    camera_id: "CAM-S01-A",
    capture_timestamp: "2026-11-25T18:30:12+07:00",
    sku_id: "Slide Sour Cream & Onion 150g",
    sku_name: "Slide Sour Cream & Onion 150g",
    unit_count: 2,
    confidence_score: 0.68,
    flag_reason: "Low Confidence",
    bounding_box: [
      [10, 20, 30, 40],
      [50, 60, 30, 40],
    ],
    frame_presigned_url: "https://example.test/frame.jpg",
    status: "Chờ duyệt",
    ...over,
  }) as never;

const row = () =>
  ({
    id: "Slide Sour Cream & Onion 150g",
    name: "Slide Sour Cream & Onion 150g",
    thumbnail: "/images/products/slide-sour-cream-onion-150g.png",
    onShelfStock: 6,
    confidence: 0.95,
    status: "Not flagged",
    detailFetchedAt: null,
    cvOutput: {
      reading_id: "RD-S01-20261126-154523-001",
      capture_id: "CAP-S01-20261126-154523",
      unit_count: 6,
      confidence_score: 0.95,
      is_flagged: false,
      flag_reason: "",
      bounding_box: [],
      frame_url: null,
      frame_w: 2560,
      frame_h: 1440,
    },
    audit: { accuracy: null, expectedLabel: "Slide Sour Cream & Onion 150g", mismatchType: "None", reviewedAt: "2026-11-24T09:00:00+07:00" },
  }) as never;

test("the card opened from a queue item shows the flagged reading, not the product's latest one", () => {
  const card = cardFromQueueItem(flagged(), row(), 1000);
  assert.equal(card.cvOutput.reading_id, "RD-S01-20261125-183012-002");
  assert.equal(card.cvOutput.capture_timestamp, "2026-11-25T18:30:12+07:00");
  assert.deepEqual([card.cvOutput.unit_count, card.cvOutput.confidence_score, card.cvOutput.bounding_box.length], [2, 0.68, 2]);
  assert.deepEqual([card.cvOutput.is_flagged, card.cvOutput.flag_reason, card.status], [true, "Low Confidence", "Low Confidence"]);
  assert.equal(card.cvOutput.frame_url, "https://example.test/frame.jpg");
});

test("that card keeps the product's own name and photo, carries the item's key and starts unreviewed", () => {
  const card = cardFromQueueItem(flagged(), row(), 1000);
  assert.deepEqual([card.id, card.thumbnail], ["Slide Sour Cream & Onion 150g", "/images/products/slide-sour-cream-onion-150g.png"]);
  assert.equal(card.reviewQueueKey, "CAM-S01-A#Slide Sour Cream & Onion 150g#Low Confidence");
  assert.deepEqual([card.audit.reviewedAt, card.audit.mismatchType, card.detailFetchedAt], [null, "None", 1000]);
});

test("a queue item whose product has no row still gets a card", () => {
  const card = cardFromQueueItem(flagged({ sku_id: "UNRECOGNIZED", sku_name: null, flag_reason: "Unrecognized", confidence_score: 0 }), undefined, 1000);
  assert.deepEqual([card.id, card.name, card.thumbnail], ["UNRECOGNIZED", "Unrecognized", "/images/products/placeholder.svg"]);
  assert.deepEqual([card.cvOutput.flag_reason, card.cvOutput.unit_count], ["Unrecognized", 2]);
  assert.equal(card.audit.expectedLabel, "");
});

test("a card opened from its row finds the waiting item of the very reading it shows", () => {
  const items = [flagged(), flagged({ queue_key: "other", reading_id: "RD-OTHER", status: "Đã xác nhận" })];
  assert.equal(queueKeyForReading(items, "RD-S01-20261125-183012-002"), "CAM-S01-A#Slide Sour Cream & Onion 150g#Low Confidence");
  assert.equal(queueKeyForReading(items, "RD-OTHER"), undefined); // already checked
  assert.equal(queueKeyForReading(items, "RD-S01-20261126-154523-001"), undefined); // a newer, unflagged reading
  assert.equal(queueKeyForReading(items, "—"), undefined);
});

test("a correction counts as changed only when the label or the mismatch type moved", () => {
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "Slide Hot & Spicy 160g", "None"), false);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "", "None"), false);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "Slide Cheese 145g", "None"), true);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "Slide Hot & Spicy 160g", "Count Mismatch"), true);
  assert.equal(correctionChanged("Slide Hot & Spicy 160g", "", "Not on the shelf (false reading)"), true);
});

test("the toast says what happened to the queue item and to the frame", () => {
  assert.equal(correctionToast(false, null), "Saved the correction.");
  assert.equal(correctionToast(false, undefined), "Saved the correction.");
  assert.equal(correctionToast(true, null), "Saved the correction. The reading is checked off in the review queue.");
  assert.equal(
    correctionToast(false, "pending"),
    "Saved the correction. Its frame goes to the labelling queue within the hour."
  );
  assert.equal(
    correctionToast(true, "pending"),
    "Saved the correction. The reading is checked off in the review queue. Its frame goes to the labelling queue within the hour."
  );
});
