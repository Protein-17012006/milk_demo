import assert from "node:assert/strict";
import { test } from "node:test";
import {
  canPutLive,
  pollDelay,
  requestStatus,
  runLine,
  runnerQuiet,
  sinceText,
  skuRows,
  statusText,
  verdictText,
  versionLabelsText,
} from "./model-versions.ts";
import type { ApiVerdict, ApiVersionsState } from "./api.ts";

const verdict = (state: ApiVerdict["state"], missing: string[] = []): ApiVerdict => ({
  state,
  missing,
  p: 0.01,
  sku_drops: [],
});

test("a waiting verdict lists what is missing", () => {
  assert.equal(
    verdictText(verdict("waiting", ["1 more day", "18 more judged frames"])),
    "Needs 1 more day and 18 more judged frames before a decision."
  );
  assert.equal(verdictText(verdict("waiting", ["3 more days"])), "Needs 3 more days before a decision.");
});

test("the three decided verdicts read plainly", () => {
  assert.equal(verdictText(verdict("better")), "Better than the live version");
  assert.equal(verdictText(verdict("no_difference")), "No difference seen");
  assert.equal(verdictText(verdict("worse")), "Worse than the live version");
});

test("a worse verdict names the products that fell behind", () => {
  assert.equal(
    verdictText({ state: "worse", missing: [], p: 0.5, sku_drops: ["original145"] }, { original145: "Slide Original 145g" }),
    "Worse than the live version: Slide Original 145g fell more than 5 points behind"
  );
});

test("put live only for an admin, when idle, on better or no difference", () => {
  assert.equal(canPutLive(verdict("better"), true, false), true);
  assert.equal(canPutLive(verdict("no_difference"), true, false), true);
  assert.equal(canPutLive(verdict("worse"), true, false), false);
  assert.equal(canPutLive(verdict("waiting"), true, false), false);
  assert.equal(canPutLive(verdict("better"), false, false), false);
  assert.equal(canPutLive(verdict("better"), true, true), false);
  assert.equal(canPutLive(null, true, false), false);
});

test("every status has its words", () => {
  assert.equal(statusText("parallel"), "Running in parallel");
  assert.equal(statusText("stopped", "too_slow"), "Stopped: too_slow");
  assert.equal(statusText("stopped"), "Stopped");
  assert.equal(statusText("discarded"), "Discarded");
  assert.equal(statusText("replaced"), "Replaced");
  assert.equal(statusText("live"), "Live");
  assert.equal(statusText("candidate"), "Waiting to start");
  assert.equal(statusText("something new"), "something new");
});

test("the run line counts days and judged frames", () => {
  assert.equal(runLine({ days: 1, frames: 1 }), "1 day, 1 frame judged");
  assert.equal(runLine({ days: 3, frames: 31 }), "3 days, 31 frames judged");
  assert.equal(runLine({ days: 0, frames: 0 }), "0 days, 0 frames judged");
});

test("a time reads as day/month hour:minute on the store's clock", () => {
  assert.equal(sinceText("2026-11-28T09:05:00+07:00"), "28/11 09:05");
  assert.equal(sinceText("2026-11-28T02:05:00Z"), "28/11 09:05");
  assert.equal(sinceText(undefined), "—");
});

test("a request waits until the counting machine has answered that very request", () => {
  const request = { id: "r2", action: "put_live" as const, version_id: "v2", by: "a@b.c", at: "2026-11-28T09:00:00+07:00" };
  const idle: ApiVersionsState = { live: "v1" };
  assert.deepEqual(requestStatus(idle), { kind: "idle" });
  assert.deepEqual(requestStatus({ ...idle, request }), { kind: "waiting" });
  const earlier = { request_id: "r1", ok: true, message: "", at: "2026-11-27T09:00:00+07:00" };
  assert.deepEqual(requestStatus({ ...idle, request, last_result: earlier }), { kind: "waiting" });
  const done = { request_id: "r2", ok: true, message: "", at: "2026-11-28T09:01:00+07:00" };
  assert.deepEqual(requestStatus({ ...idle, request, last_result: done }), { kind: "idle" });
  const failed = { ...done, ok: false, message: "The worker did not start with v2: it has written no start record." };
  assert.deepEqual(requestStatus({ ...idle, request, last_result: failed }), {
    kind: "failed",
    message: "The worker did not start with v2: it has written no start record.",
  });
});

test("the product table goes by units judged, with names where they are known", () => {
  const perSku = {
    cheese145: { units: 3, live_right: 1, cand_right: 2 },
    original145: { units: 12, live_right: 5, cand_right: 11 },
  };
  assert.deepEqual(skuRows(perSku, { original145: "Slide Original 145g" }), [
    { key: "original145", name: "Slide Original 145g", units: 12, liveRight: 5, candRight: 11 },
    { key: "cheese145", name: "cheese145", units: 3, liveRight: 1, candRight: 2 },
  ]);
  assert.deepEqual(skuRows({}, {}), []);
});

test("the counting machine counts as quiet when it has not been seen for three minutes", () => {
  const now = Date.parse("2026-11-28T09:10:00+07:00");
  assert.equal(runnerQuiet("2026-11-28T09:08:30+07:00", now), false);
  assert.equal(runnerQuiet("2026-11-28T09:06:59+07:00", now), true);
  assert.equal(runnerQuiet(undefined, now), true);
  assert.equal(runnerQuiet("not a time", now), true);
});

test("the block looks again quickly only while a live machine is working on a fresh request", () => {
  assert.equal(pollDelay({ waiting: true, quiet: false, waitedMs: 20_000 }), 5_000);
  assert.equal(pollDelay({ waiting: true, quiet: true, waitedMs: 20_000 }), 60_000);
  assert.equal(pollDelay({ waiting: true, quiet: false, waitedMs: 3 * 60_000 }), 60_000);
  assert.equal(pollDelay({ waiting: false, quiet: false, waitedMs: 0 }), 60_000);
});

test("a version says whether people's labels are in it", () => {
  assert.equal(versionLabelsText({}), "No people's labels in this version.");
  assert.equal(versionLabelsText({ label_frames: 0 }), "No people's labels in this version.");
  assert.equal(versionLabelsText({ label_frames: 60, labellers: 3 }), "Trained with 60 labelled frames from 3 people.");
  assert.equal(versionLabelsText({ label_frames: 1, labellers: 1 }), "Trained with 1 labelled frame from 1 person.");
  assert.equal(versionLabelsText({ label_frames: 60 }), "Trained with 60 labelled frames.");
});
