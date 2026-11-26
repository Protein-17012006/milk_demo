// Unit tests for labelling one frame on the Model page (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import { canSave, labelQueueOrder, nextVerdict, relabelQueue, toPayload, totalsBySku } from "./audit-labeling.ts";
import type { BoxLabel, RelabelCandidate } from "./audit-labeling.ts";

const twoHot = [
  { box_id: 1, sku_id: "hot160" },
  { box_id: 2, sku_id: "hot160" },
];

test("a click walks a box through every verdict and back to unlabelled", () => {
  assert.equal(nextVerdict(null), "correct");
  assert.equal(nextVerdict("correct"), "wrong_sku");
  assert.equal(nextVerdict("wrong_sku"), "not_product");
  assert.equal(nextVerdict("not_product"), "out_of_scope");
  assert.equal(nextVerdict("out_of_scope"), null);
});

test("totals per SKU count right boxes, relabelled boxes and missed units", () => {
  const labels: Record<number, BoxLabel> = {
    1: { verdict: "correct", trueSku: null },
    2: { verdict: "wrong_sku", trueSku: "original145" },
  };
  assert.deepEqual(totalsBySku(twoHot, labels, [{ sku_id: "hot160" }]), {
    hot160: { model: 2, truth: 2 },
    original145: { model: 0, truth: 1 },
  });
});

test("an UNRECOGNIZED box judged right counts for no SKU", () => {
  const labels: Record<number, BoxLabel> = { 1: { verdict: "correct", trueSku: null } };
  assert.deepEqual(totalsBySku([{ box_id: 1, sku_id: null }], labels, []), {});
});

test("save needs a verdict on every box and the right SKU on wrong ones", () => {
  assert.equal(canSave(twoHot, { 1: { verdict: "correct", trueSku: null } }, true), false);
  assert.equal(
    canSave(twoHot, {
      1: { verdict: "correct", trueSku: null },
      2: { verdict: "wrong_sku", trueSku: null },
    }, true),
    false
  );
  assert.equal(
    canSave(twoHot, {
      1: { verdict: "correct", trueSku: null },
      2: { verdict: "not_product", trueSku: null },
    }, true),
    true
  );
  assert.equal(canSave([], {}, true), true); // a frame with no boxes is saved with its missed units only
});

test("the payload sends the right SKU only for wrong boxes and rounds the missed points", () => {
  const labels: Record<number, BoxLabel> = {
    1: { verdict: "correct", trueSku: "ignored" },
    2: { verdict: "wrong_sku", trueSku: "original145" },
  };
  assert.deepEqual(toPayload(labels, [{ sku_id: "hot160", x: 940.6, y: 400.2 }]), {
    verdicts: [
      { box_id: 1, verdict: "correct" },
      { box_id: 2, verdict: "wrong_sku", true_sku_id: "original145" },
    ],
    missed: [{ sku_id: "hot160", x: 941, y: 400 }],
    misses_checked: true,
  });
});

test("a click goes from not our SKU to out of scope, then back to unlabelled", () => {
  assert.equal(nextVerdict("not_product"), "out_of_scope");
  assert.equal(nextVerdict("out_of_scope"), null);
});

test("save needs every box labelled and the missed-cans check", () => {
  const boxes = [{ box_id: 1, sku_id: "hot160" }];
  const labels = { 1: { verdict: "out_of_scope" as const, trueSku: null } };
  assert.equal(canSave(boxes, labels, false), false);
  assert.equal(canSave(boxes, labels, true), true);
});

test("an out-of-scope box counts neither for the model nor for the truth", () => {
  assert.deepEqual(totalsBySku([{ box_id: 1, sku_id: "cheese145" }], { 1: { verdict: "out_of_scope", trueSku: null } }, []), {});
});

test("Relabel them opens the done scoring frames labelled before rule B, oldest first", () => {
  const frame = (audit_id: string, capture_timestamp: string, fields: Partial<RelabelCandidate> = {}) =>
    ({ audit_id, capture_timestamp, purpose: "scoring", status: "done", label_rule: null, ...fields }) as RelabelCandidate;
  assert.deepEqual(
    relabelQueue([
      frame("AUD-20261124-12", "2026-11-24T12:05:00+07:00"),
      frame("AUD-20261123-17", "2026-11-23T17:44:38+07:00"),
      frame("AUD-20261123-18", "2026-11-23T18:49:00+07:00", { label_rule: "B" }), // already under rule B
      frame("AUD-20261123-19", "2026-11-23T19:13:00+07:00", { label_rule: "A" }), // rule A left out the milk
      frame("TRN-20261123-09", "2026-11-23T09:00:00+07:00", { purpose: "training" }), // never scored
      frame("AUD-20261123-08", "2026-11-23T08:00:00+07:00", { status: "pending" }), // not labelled yet
    ]),
    ["AUD-20261123-17", "AUD-20261123-19", "AUD-20261124-12"]
  );
  assert.deepEqual(relabelQueue([]), []);
});

test("the payload says the missed cans were checked", () => {
  assert.deepEqual(toPayload({ 1: { verdict: "out_of_scope", trueSku: null } }, []), {
    verdicts: [{ box_id: 1, verdict: "out_of_scope" }],
    missed: [],
    misses_checked: true,
  });
});

test("a box that needs a flavour never offers Right", () => {
  assert.equal(nextVerdict(null, true), "wrong_sku");
  assert.equal(nextVerdict("wrong_sku", true), "not_product");
  assert.equal(nextVerdict("not_product", true), "out_of_scope");
  assert.equal(nextVerdict("out_of_scope", true), null);
  assert.equal(nextVerdict(null), "correct");
});

test("the queue opens scoring, then training, then review frames, each oldest first", () => {
  const it = (audit_id: string, purpose: "scoring" | "training" | "review", capture_timestamp: string) => ({
    audit_id,
    purpose,
    capture_timestamp,
  });
  assert.deepEqual(
    labelQueueOrder([
      it("R1", "review", "2026-11-24T10:00:00+07:00"),
      it("T1", "training", "2026-11-25T10:00:00+07:00"),
      it("A2", "scoring", "2026-11-25T09:00:00+07:00"),
      it("A1", "scoring", "2026-11-24T09:00:00+07:00"),
      it("T0", "training", "2026-11-23T10:00:00+07:00"),
    ]),
    ["A1", "A2", "T0", "T1", "R1"]
  );
});

test("a review frame saves with its pre-filled Right boxes and every ? box decided", () => {
  const boxes = [
    { box_id: 1, sku_id: null },
    { box_id: 2, sku_id: "hot160" },
  ];
  const labels: Record<number, BoxLabel> = {
    1: { verdict: "wrong_sku", trueSku: "original145" },
    2: { verdict: "correct", trueSku: null },
  };
  assert.equal(canSave(boxes, labels, true), true);
  assert.equal(canSave(boxes, { 2: labels[2] }, true), false);
});
