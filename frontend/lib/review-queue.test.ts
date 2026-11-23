// Unit tests for the Products review queue summary (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import { orderForReview, reviewSummary } from "./review-queue.ts";

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
