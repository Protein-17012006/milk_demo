/**
 * Text helpers for the Dashboard's shelf numbers: filters, events, changes against the previous period and the
 * line a blocked card shows. Definitions: docs/superpowers/specs/2026-11-24-dashboard-shelf-metrics-design.md.
 */

import type { ApiShelfEvent, BlockedReason, ShelfEventType } from "./api";

export const TIMEFRAMES: { label: string; days: number }[] = [
  { label: "Today", days: 1 },
  { label: "Last 7 days", days: 7 },
  { label: "Last 14 days (one cycle)", days: 14 },
  { label: "Last 90 days", days: 90 },
];
export const DEFAULT_DAYS = 14;

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
