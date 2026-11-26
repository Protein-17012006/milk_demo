/**
 * Text helpers for the Dashboard's shelf numbers: filters, events, changes against the previous period and the
 * line a blocked card shows. Definitions: docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md.
 */

import type { ApiAlertAccuracy, ApiCoverage, ApiDisplayStatus, ApiShelfEvent, BlockedReason, ShelfEventType } from "./api";

export const TIMEFRAMES: { label: string; days: number }[] = [
  { label: "Today", days: 1 },
  { label: "Last 7 days", days: 7 },
  { label: "Last 14 days (one cycle)", days: 14 },
  { label: "Last 90 days", days: 90 },
];
export const DEFAULT_DAYS = 14;

const ALERT_MIN_VERIFIED = 10;
const MINUS = "−";
const signed = (n: number) => (n < 0 ? `${MINUS}${Math.abs(n)}` : `+${n}`);

const LABELS: Record<ShelfEventType, string> = {
  OOS: "OOS",
  LOW_STOCK: "LOW STOCK",
  DEPLETED: "DEPLETED",
  RESTOCKED: "RESTOCKED",
};

export const eventLabel = (type: ShelfEventType) => LABELS[type] ?? type;

/** "0 units (−6)", "+16 units (24 total)", "−4 units (8 left)", "2 left (−6)". */
export function eventText(e: Pick<ApiShelfEvent, "type" | "delta" | "level_after">): string {
  switch (e.type) {
    case "OOS":
      return `0 units (${signed(e.delta)})`;
    case "RESTOCKED":
      return `${signed(e.delta)} units (${e.level_after} total)`;
    case "DEPLETED":
      return `${signed(e.delta)} units (${e.level_after} left)`;
    case "LOW_STOCK":
      return `${e.level_after} left (${signed(e.delta)})`;
  }
}

/** " · out of stock 80 min" for a RESTOCKED that ended an out-of-stock; "" otherwise. The API leaves the field out
 * when it is empty (DynamoDB keeps no nulls), so a missing field counts as none. */
export function oosDurationText(e: { duration_min?: number | null }): string {
  return typeof e.duration_min === "number" ? ` · out of stock ${e.duration_min} min` : "";
}

/** Age of a bucket "YYYYMMDD-HHMM" (UTC+7): "10 min ago", "1 hr ago", "2 days ago". */
export function timeAgo(at: string, now: Date): string {
  const t = new Date(`${at.slice(0, 4)}-${at.slice(4, 6)}-${at.slice(6, 8)}T${at.slice(9, 11)}:${at.slice(11, 13)}:00+07:00`);
  const minutes = Math.floor((now.getTime() - t.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

/** Change of a share in percentage points: "+4.0 pts"; null without both values. */
export function ptsChange(current: number | null, previous: number | null): string | null {
  if (current === null || previous === null) return null;
  const pts = (current - previous) * 100;
  return `${pts < 0 ? MINUS : "+"}${Math.abs(pts).toFixed(1)} pts`;
}

/** A percent change from the API: "+34%", "−12.5%"; null when there is nothing to compare. */
export function pctChange(pct: number | null): string | null {
  if (pct === null) return null;
  const abs = Math.abs(pct);
  return `${pct < 0 ? MINUS : "+"}${Number.isInteger(abs) ? abs : abs.toFixed(1)}%`;
}

/** What a blocked card says, so the reader knows what to do. */
export function blockedText(reason: BlockedReason | string, storeName?: string): string {
  switch (reason) {
    case "no_hours":
      return storeName ? `Set opening hours for ${storeName} in Settings` : "Set the store's opening hours in Settings";
    case "no_expected":
      return "Choose this store's SKUs in Settings";
    case "no_checks":
      return "No checks in this period";
    case "no_previous":
      return "Needs the previous period's data to compare";
    case "no_labels":
      return "Label frames on the Model page";
    default:
      return "No data yet";
  }
}

/** "20:30" for the end of bucket "YYYYMMDD-HHMM" (its start plus 5 minutes). */
function bucketEnd(bucket: string): string {
  const total = Number(bucket.slice(9, 11)) * 60 + Number(bucket.slice(11, 13)) + 5;
  const h = Math.floor(total / 60) % 24;
  return `${String(h).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/** "between 20:30 and 08:45 (not measured)" for an event that came after a gap, from the end of the last measured
 * check before it to the start of the first one after; null for an event with no gap. */
export function gapText(e: { after_gap?: boolean; gap_from?: string; gap_to?: string }): string | null {
  if (!e.after_gap || !e.gap_from || !e.gap_to) return null;
  return `between ${bucketEnd(e.gap_from)} and ${e.gap_to.slice(9, 11)}:${e.gap_to.slice(11, 13)} (not measured)`;
}

/** "Measured 9.5 h of 12.5 h open · display not in view 1 h"; the second part only when the display was away. */
export function coverageText(c: ApiCoverage): string {
  const base = `Measured ${c.measured_hours} h of ${c.open_hours} h open`;
  return c.display_away_hours > 0 ? `${base} · display not in view ${c.display_away_hours} h` : base;
}

/** Head line of Recent Shelf Activities: how often the alerts the team checked were right. Null without the
 * number (an older backend). Below 10 confirmed events it says there are too few and, for those who can
 * confirm, how many more are needed; never a percentage. */
export function alertAccuracyText(
  a: (Partial<ApiAlertAccuracy> & { n: number }) | null | undefined,
  canConfirm = false
): string | null {
  if (!a) return null;
  const unsure = (a.unsure ?? 0) > 0 ? ` (${a.unsure} unsure)` : "";
  if (a.value == null || a.blocked_reason) {
    const more = Math.max(1, ALERT_MIN_VERIFIED - a.n);
    const ask = canConfirm
      ? ` · confirm ${more} more ${more === 1 ? "alert" : "alerts"} to see how often they are right`
      : "";
    return `Too few confirmed alerts to rate them (${a.n} so far)${ask}${unsure}`;
  }
  return `Alerts confirmed right: ${Math.round(a.value * a.n)} of ${a.n}${unsure}`;
}

const TYPE_NAMES: [string, string][] = [
  ["OOS", "OOS"],
  ["LOW_STOCK", "Low stock"],
  ["DEPLETED", "Depleted"],
  ["RESTOCKED", "Restocked"],
];

/** "OOS 7 of 9 · Restocked 3 of 4": right of right + wrong for each kind of event; kinds with none left out. */
export function alertAccuracyByTypeText(byType: ApiAlertAccuracy["by_type"] | null | undefined): string | null {
  const parts = TYPE_NAMES.flatMap(([type, name]) => {
    const c = byType?.[type];
    const n = c ? c.right + c.wrong : 0;
    return c && n > 0 ? [`${name} ${c.right} of ${n}`] : [];
  });
  return parts.length ? parts.join(" · ") : null;
}

/** The time of day "HH:MM" of an ISO timestamp written in UTC+7. */
const clock = (iso: string) => iso.slice(11, 16);

/** One line for each camera that cannot see the display; null when every camera does. After captures out of order
 * `since` can come before `last_visible_at`, so the line starts at the later of the two. */
export function displayBanner(displays: ApiDisplayStatus[]): string | null {
  const lines = displays
    .filter((d) => !d.visible)
    .map((d) => {
      const last = d.last_visible_at;
      const since = d.since && last && last > d.since ? last : (d.since ?? last);
      const from = since ? ` since ${clock(since)}` : "";
      const tail = last ? `numbers below are from the last check at ${clock(last)}` : "there is no earlier check to show";
      return `${d.camera_id} cannot see the display${from} — ${tail}`;
    });
  return lines.length ? lines.join("\n") : null;
}

export interface DashboardQuery {
  days?: number;
  storeId?: string;
  category?: string;
  kind?: string;
  limit?: number;
  cursor?: string;
  metric?: string;
}

/** The Dashboard filters as a query string for the API; unset values are left out. */
export function dashboardQuery(q: DashboardQuery): string {
  const sp = new URLSearchParams();
  const pairs: [string, string | number | undefined][] = [
    ["metric", q.metric],
    ["days", q.days],
    ["store_id", q.storeId],
    ["category", q.category],
    ["kind", q.kind],
    ["limit", q.limit],
    ["cursor", q.cursor],
  ];
  for (const [key, value] of pairs) {
    if (value !== undefined && value !== "") sp.set(key, String(value));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** The Restock Rate card's small print. The rate is per day that has checks (an older backend does not say how
 * many: measuredDays undefined), so a camera that ran 5 of the 14 days is not averaged over 14. */
export function restockDefinition(days: number, measuredDays: number | undefined): string {
  if (days === 1) return "Units restocked today, against yesterday.";
  const over = measuredDays === undefined ? "" : ` that has checks (${measuredDays} of the last ${days} days)`;
  return `Units restocked per day${over}, against the ${days} days before.`;
}

/** A shelf event with the earlier events it stands for. */
export interface EventFold<T> {
  head: T;
  earlier: T[];
}

/**
 * Folds repeats in a list of events (newest first): an event joins the fold of the same store, product and type
 * unless an event of another type for that store and product lies between them. So five LOW STOCK rows of one
 * product read as one row with "+4 earlier", while LOW, RESTOCKED, LOW stay three rows. Folds keep the place of
 * their newest event.
 */
export function foldEvents<T extends { store_id: string; sku_id: string; type: string }>(items: T[]): EventFold<T>[] {
  const folds: EventFold<T>[] = [];
  const latest = new Map<string, EventFold<T>>(); // per store and product: the fold a same-type event still joins
  for (const item of items) {
    const key = `${item.store_id}|${item.sku_id}`;
    const fold = latest.get(key);
    if (fold && fold.head.type === item.type) {
      fold.earlier.push(item);
      continue;
    }
    const started: EventFold<T> = { head: item, earlier: [] };
    folds.push(started);
    latest.set(key, started);
  }
  return folds;
}

/** The label of the button that unfolds a row; null when there is nothing to unfold. */
export function earlierText(count: number): string | null {
  return count > 0 ? `+${count} earlier` : null;
}
