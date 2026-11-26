import assert from "node:assert/strict";
import { test } from "node:test";
import { unconfirmedEvents, waitingWork } from "./waiting-work.ts";

test("waiting work is listed as links, and nothing waiting lists nothing", () => {
  assert.deepEqual(waitingWork({ readings: 9, frames: 13, events: 4 }), [
    { key: "readings", text: "9 readings to review", href: "/category" },
    { key: "frames", text: "13 frames to label", href: "/model" },
    { key: "events", text: "4 shelf events to confirm", href: "#recent-shelf-activities" },
  ]);
  assert.deepEqual(waitingWork({ readings: 1, frames: 0, events: null }), [
    { key: "readings", text: "1 reading to review", href: "/category" },
  ]);
  assert.deepEqual(waitingWork({ readings: 0, frames: 1, events: 1 }), [
    { key: "frames", text: "1 frame to label", href: "/model" },
    { key: "events", text: "1 shelf event to confirm", href: "#recent-shelf-activities" },
  ]);
  assert.deepEqual(waitingWork({ readings: 0, frames: 0, events: 0 }), []);
  assert.deepEqual(waitingWork({ readings: null, frames: null, events: null }), []);
  assert.equal(
    waitingWork({ readings: 0, frames: 0, events: 20, moreEvents: true })[0].text,
    "20+ shelf events to confirm"
  );
});

test("an event waits until someone gives a verdict", () => {
  assert.equal(unconfirmedEvents([{ verdict: "right" }, {}, { verdict: undefined }, { verdict: "unsure" }]), 2);
  assert.equal(unconfirmedEvents([]), 0);
});
