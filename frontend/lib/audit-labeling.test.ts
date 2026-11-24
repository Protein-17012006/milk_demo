// Unit tests for labelling one frame on the Model page (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import { canSave, nextVerdict, toPayload, totalsBySku } from "./audit-labeling.ts";
import type { BoxLabel } from "./audit-labeling.ts";

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

test("the payload says the missed cans were checked", () => {
  assert.deepEqual(toPayload({ 1: { verdict: "out_of_scope", trueSku: null } }, []), {
    verdicts: [{ box_id: 1, verdict: "out_of_scope" }],
    missed: [],
    misses_checked: true,
  });
});
