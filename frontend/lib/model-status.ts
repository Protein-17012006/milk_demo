// "Are the camera and the worker running?", answered from the time of a store's latest image.
// An image reaches the backend only when the camera, the hub and the worker all did their part, so a fresh image
// means the whole chain runs. No fresh image is normal while the store is closed (the hub is off at night) and
// worth a look while it is open. Times are read on the store's clock (UTC+7).

export type RunTone = "running" | "quiet" | "stopped" | "none";

export interface RunStatus {
  tone: RunTone;
  text: string;
}

/** The worker samples the stream every 5 minutes, so an image within 15 minutes means it is running. */
export const RUNNING_WITHIN_MIN = 15;

const ICT_OFFSET_MS = 7 * 3_600_000;
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

const ictStamp = (moment: Date) => new Date(moment.getTime() + ICT_OFFSET_MS).toISOString();

/** "15:45" for an image of today (UTC+7), "15:45 on 26/11" for an older one. timestamp: ISO in UTC+7. */
export function imageTimeText(timestamp: string, now: Date): string {
  const time = timestamp.slice(11, 16);
  if (timestamp.slice(0, 10) === ictStamp(now).slice(0, 10)) return time;
  return `${time} on ${timestamp.slice(8, 10)}/${timestamp.slice(5, 7)}`;
}

/** "3 min", "4 h", "3 days": minutes to the nearest one, hours and days rounded down. */
function ageOf(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(ms / 3_600_000);
  if (hours < 48) return `${hours} h`;
  return `${Math.floor(hours / 24)} days`;
}

/** What the latest image of a store says about its camera, hub and worker. */
export function runStatus(
  store: { last_capture_timestamp: string | null; open_time?: string | null; close_time?: string | null },
  now: Date
): RunStatus {
  const latest = store.last_capture_timestamp;
  const taken = latest ? Date.parse(latest) : NaN;
  if (!latest || Number.isNaN(taken)) return { tone: "none", text: "No image in the last 7 days." };

  const ageMs = Math.max(0, now.getTime() - taken);
  const at = imageTimeText(latest, now);
  if (ageMs <= RUNNING_WITHIN_MIN * 60_000) {
    return { tone: "running", text: `Running: latest image at ${at} (${ageOf(ageMs)} ago).` };
  }

  const open = store.open_time ?? "";
  const close = store.close_time ?? "";
  // hours that are missing, malformed or the wrong way round say nothing about "open now"
  const hoursKnown = HHMM.test(open) && HHMM.test(close) && open < close;
  if (!hoursKnown) return { tone: "quiet", text: `Latest image at ${at} (${ageOf(ageMs)} ago).` };

  const clock = ictStamp(now).slice(11, 16);
  if (clock >= open && clock < close) {
    return {
      tone: "stopped",
      text: `No new image for ${ageOf(ageMs)} (latest at ${at}). The store is open until ${close}, so the camera, the hub or the worker may have stopped.`,
    };
  }
  return {
    tone: "quiet",
    text: `Latest image at ${at} (${ageOf(ageMs)} ago). The store is closed now and opens at ${open}.`,
  };
}
