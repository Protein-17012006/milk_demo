/**
 * Words and small rules for the Model page's "Model versions" block: the live version, the candidate that runs in
 * parallel with it, and what a team admin may ask for. The backend decides what is allowed (model_versions.can);
 * these only say what to show.
 */
// Imports are type-only so Node can run the unit tests without the Next.js path aliases.
import type { ApiVerdict, ApiVersionTally, ApiVersionsState } from "./api";

const STATUS: Record<string, string> = {
  candidate: "Waiting to start",
  parallel: "Running in parallel",
  live: "Live",
  replaced: "Replaced",
  discarded: "Discarded",
  stopped: "Stopped",
};

/** A version's status in words; a stopped one says why when the reason is known. */
export function statusText(status: string, reason?: string | null): string {
  if (status === "stopped" && reason) return `Stopped: ${reason}`;
  return STATUS[status] ?? status;
}

/** How the parallel run stands, as one sentence. `names` gives product names for model labels. */
export function verdictText(v: ApiVerdict, names: Record<string, string> = {}): string {
  if (v.state === "waiting") return `Needs ${v.missing.join(" and ")} before a decision.`;
  if (v.state === "better") return "Better than the live version";
  if (v.state === "no_difference") return "No difference seen";
  const fell = v.sku_drops.map((sku) => names[sku] ?? sku);
  return fell.length
    ? `Worse than the live version: ${fell.join(", ")} fell more than 5 points behind`
    : "Worse than the live version";
}

/** Whether the "Put live" button is enabled. */
export function canPutLive(v: ApiVerdict | null, isAdmin: boolean, busy: boolean): boolean {
  return isAdmin && !busy && v !== null && (v.state === "better" || v.state === "no_difference");
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "3 days, 31 frames judged". */
export function runLine(tally: Pick<ApiVersionTally, "days" | "frames">): string {
  return `${plural(tally.days, "day", "days")}, ${plural(tally.frames, "frame", "frames")} judged`;
}

const two = (n: number) => String(n).padStart(2, "0");

/** A moment as "28/11 09:05" on the store's clock (UTC+7), whatever offset it was written with. */
export function sinceText(iso?: string | null): string {
  const ms = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(ms)) return "—";
  const d = new Date(ms + 7 * 3600 * 1000);
  return `${two(d.getUTCDate())}/${two(d.getUTCMonth() + 1)} ${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`;
}

export type RequestStatus = { kind: "idle" } | { kind: "waiting" } | { kind: "failed"; message: string };

/** Where the request in hand stands: the counting machine answers it by writing last_result with its id. */
export function requestStatus(state: ApiVersionsState): RequestStatus {
  const request = state.request;
  if (!request) return { kind: "idle" };
  const result = state.last_result;
  if (!result || result.request_id !== request.id) return { kind: "waiting" };
  return result.ok ? { kind: "idle" } : { kind: "failed", message: result.message };
}

const QUIET_AFTER_MS = 3 * 60 * 1000; // the counting machine writes a sign of life every minute
const QUICK_FOR_MS = 2 * 60 * 1000; // a request is done within about a minute; after that, look less often

/** Whether the counting machine has stopped giving signs of life (or never gave one). */
export function runnerQuiet(seenAt: string | null | undefined, nowMs: number): boolean {
  const seen = seenAt ? Date.parse(seenAt) : NaN;
  return Number.isNaN(seen) || nowMs - seen > QUIET_AFTER_MS;
}

/** How long the block waits before it reads again: quickly only while a live machine works on a fresh request. */
export function pollDelay(p: { waiting: boolean; quiet: boolean; waitedMs: number }): number {
  return p.waiting && !p.quiet && p.waitedMs < QUICK_FOR_MS ? 5000 : 60000;
}

export interface SkuRow {
  key: string;
  name: string;
  units: number;
  liveRight: number;
  candRight: number;
}

/** The comparison per product, most judged units first. */
export function skuRows(perSku: ApiVersionTally["per_sku"], names: Record<string, string>): SkuRow[] {
  return Object.entries(perSku)
    .map(([key, row]) => ({
      key,
      name: names[key] ?? key,
      units: row.units,
      liveRight: row.live_right,
      candRight: row.cand_right,
    }))
    .sort((a, b) => b.units - a.units || a.name.localeCompare(b.name));
}
