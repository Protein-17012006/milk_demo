// Unit tests for the frame viewer's zoom region (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import { focusRegion } from "./frame-geometry.ts";

const near = (a: number, b: number) => Math.abs(a - b) < 0.01;

test("one small box: min width 1/6 frame, 16:9, centred on the box", () => {
  // box centre (958 + 24, 277 + 6) = (982, 283); 1/6 of 2560×1440 is 426.67×240
  const r = focusRegion([[958, 277, 48, 12]], 2560, 1440);
  assert.ok(near(r.w, 2560 / 6) && near(r.h, 1440 / 6), JSON.stringify(r));
  assert.ok(near(r.x + r.w / 2, 982) && near(r.y + r.h / 2, 283), JSON.stringify(r));
});

test("margin is the largest box side on every side", () => {
  // tall box 20×300: margin 300 → 620×900, widened to 16:9 → 1600×900 around (1010, 650)
  const r = focusRegion([[1000, 500, 20, 300]], 2560, 1440);
  assert.ok(near(r.w, 1600) && near(r.h, 900), JSON.stringify(r));
  assert.ok(near(r.x, 210) && near(r.y, 200), JSON.stringify(r));
});

test("box at the top edge stays inside the frame", () => {
  const r = focusRegion([[464, 1, 57, 40]], 2560, 1440);
  assert.ok(r.y >= 0 && r.y + r.h <= 1440 && r.x >= 0 && r.x + r.w <= 2560, JSON.stringify(r));
  assert.ok(near(r.y, 0) && near(r.h, 240), JSON.stringify(r)); // shifted down, size kept
});

test("no boxes gives the full frame", () => {
  assert.deepEqual(focusRegion([], 2560, 1440), { x: 0, y: 0, w: 2560, h: 1440 });
});

test("boxes spread over the frame give the full frame", () => {
  assert.deepEqual(focusRegion([[0, 0, 100, 100], [2400, 1300, 150, 130]], 2560, 1440), { x: 0, y: 0, w: 2560, h: 1440 });
});
