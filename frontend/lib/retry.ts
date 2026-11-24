/**
 * Retrying reads when AWS is busy. The account runs at most 10 Lambda calls at once, and the Dashboard asks for about
 * 9 numbers together, so a call is sometimes throttled. API Gateway then answers 500 without CORS headers, which the
 * browser reports as a failed fetch (a thrown TypeError). Only use this for reads (GET): they are safe to repeat.
 */

export const READ_RETRY_DELAYS_MS = [400, 1200];

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Runs `send`, and again after each delay while it throws or answers 5xx/429; returns the last answer or throws. */
export async function retryRead(
  send: () => Promise<Response>,
  delays: number[] = READ_RETRY_DELAYS_MS,
  wait: (ms: number) => Promise<void> = sleep
): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    const last = attempt >= delays.length;
    try {
      const res = await send();
      if (last || (res.status < 500 && res.status !== 429)) return res;
    } catch (err) {
      if (last) throw err;
    }
    await wait(delays[attempt]);
  }
}
