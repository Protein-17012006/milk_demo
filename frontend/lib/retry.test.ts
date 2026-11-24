// Unit tests for retrying reads when AWS Lambda is busy (run: npm test).
import { test } from "node:test";
import assert from "node:assert/strict";
import { retryRead } from "./retry.ts";

const res = (status: number) => ({ status }) as Response;
const noWait = async () => {};

test("retryRead: a 5xx or 429 is tried again, then the good answer is returned", async () => {
  const answers = [res(500), res(429), res(200)];
  let calls = 0;
  const got = await retryRead(async () => answers[calls++], [10, 10], noWait);
  assert.equal(got.status, 200);
  assert.equal(calls, 3);
});

test("retryRead: a thrown network error (a throttled call fails CORS in the browser) is tried again", async () => {
  let calls = 0;
  const got = await retryRead(
    async () => {
      calls++;
      if (calls === 1) throw new TypeError("Failed to fetch");
      return res(200);
    },
    [10],
    noWait
  );
  assert.equal(got.status, 200);
  assert.equal(calls, 2);
});

test("retryRead: 4xx answers are not retried; after the last try the last answer or error is passed on", async () => {
  let calls = 0;
  assert.equal((await retryRead(async () => (calls++, res(404)), [10, 10], noWait)).status, 404);
  assert.equal(calls, 1);

  calls = 0;
  assert.equal((await retryRead(async () => (calls++, res(503)), [10, 10], noWait)).status, 503);
  assert.equal(calls, 3);

  calls = 0;
  await assert.rejects(
    retryRead(async () => {
      calls++;
      throw new TypeError("Failed to fetch");
    }, [10], noWait),
    TypeError
  );
  assert.equal(calls, 2);
});

test("retryRead: waits the given delays between tries", async () => {
  const waited: number[] = [];
  await retryRead(async () => res(500), [300, 900], async (ms) => {
    waited.push(ms);
  });
  assert.deepEqual(waited, [300, 900]);
});
