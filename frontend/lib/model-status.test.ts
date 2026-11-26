import assert from "node:assert/strict";
import { test } from "node:test";
import { imageTimeText, runStatus } from "./model-status.ts";

const NOW = new Date("2026-11-26T13:40:00Z"); // 20:40 on 26/11 in UTC+7
const HOURS = { open_time: "06:00", close_time: "22:00" };

test("an image of the last 15 minutes means it is running", () => {
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T20:37:10+07:00", ...HOURS }, NOW), {
    tone: "running",
    text: "Running: latest image at 20:37 (3 min ago).",
  });
});

test("no new image while the store is open is flagged", () => {
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T15:45:23+07:00", ...HOURS }, NOW), {
    tone: "stopped",
    text: "No new image for 4 h (latest at 15:45). The store is open until 22:00, so the camera, the hub or the worker may have stopped.",
  });
});

test("a closed store is quiet, not stopped", () => {
  const early = new Date("2026-11-26T22:10:00Z"); // 05:10 on 27/11 in UTC+7
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T21:58:02+07:00", ...HOURS }, early), {
    tone: "quiet",
    text: "Latest image at 21:58 on 26/11 (7 h ago). The store is closed now and opens at 06:00.",
  });
});

test("without opening hours it only says what it knows", () => {
  assert.deepEqual(runStatus({ last_capture_timestamp: "2026-11-26T15:45:23+07:00" }, NOW), {
    tone: "quiet",
    text: "Latest image at 15:45 (4 h ago).",
  });
  assert.deepEqual(runStatus({ last_capture_timestamp: null, ...HOURS }, NOW), {
    tone: "none",
    text: "No image in the last 7 days.",
  });
  // hours written the wrong way round are not "open all day"
  const backwards = { last_capture_timestamp: "2026-11-26T15:45:23+07:00", open_time: "22:00", close_time: "06:00" };
  assert.equal(runStatus(backwards, NOW).tone, "quiet");
});

test("an old image counts its age in days", () => {
  const status = runStatus({ last_capture_timestamp: "2026-11-23T09:00:00+07:00" }, NOW);
  assert.equal(status.text, "Latest image at 09:00 on 23/11 (3 days ago).");
});

test("the time of an image", () => {
  assert.equal(imageTimeText("2026-11-26T15:45:23+07:00", NOW), "15:45");
  assert.equal(imageTimeText("2026-11-24T09:05:00+07:00", NOW), "09:05 on 24/11");
});
