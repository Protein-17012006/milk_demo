// What is on the shelf now, product by product: the rows of the Dashboard's table, their totals and labels, the
// line that says when the numbers were read, and the legend of the shelf photo.
// The numbers are the latest reading of each product (GET /products), the same ones the Category page lists. The
// backend says which products are on the shelf plan and how each one's stock stands; nothing here recomputes that.
// Imports are type-only so Node can run the unit tests without the Next.js path aliases.
import type { ReliabilityBadge } from "./api";
import type { Box } from "./frame-geometry";

export type StockStatus = "OOS" | "LOW" | "IN_STOCK" | "NOT_IN_VIEW";

/** A plan product whose place is not in the camera's view: since when, and the last thing seen there. */
export interface NotInView {
  since: string;
  lastUnits: number | null;
  lastAt: string | null;
}

/** The fields of a GET /products item the table reads; an older backend leaves out the plan and the status. */
export interface ShelfNowInput {
  sku_id: string;
  sku_name: string;
  image_url?: string | null;
  unit_count: number;
  in_shelf_plan?: boolean;
  stock_status?: StockStatus | null;
  not_in_view?: { since: string; last_units: number | null; last_at: string | null } | null;
  reliability?: { badge: ReliabilityBadge } | null;
}

export interface ShelfNowRow {
  skuId: string;
  name: string;
  imageUrl: string | null;
  units: number;
  status: StockStatus;
  badge: ReliabilityBadge | null;
  /** Set when status is NOT_IN_VIEW; then units is the last reading, not today's stock. */
  notInView: NotInView | null;
}

const ATTENTION: Record<StockStatus, number> = { OOS: 0, LOW: 1, NOT_IN_VIEW: 2, IN_STOCK: 3 };

function shownUnits(r: ShelfNowRow): number {
  return r.status === "NOT_IN_VIEW" ? 0 : r.units;
}

/** Products of the shelf plan: out of stock first, then low, then not in view, then in stock; fewer units first
 * (a product not in view counts as none); then by name. */
export function shelfNowRows(products: ShelfNowInput[]): ShelfNowRow[] {
  return products
    .filter((p) => p.in_shelf_plan === true && p.stock_status != null)
    .map((p) => ({
      skuId: p.sku_id,
      name: p.sku_name,
      imageUrl: p.image_url ?? null,
      units: p.unit_count,
      status: p.stock_status as StockStatus,
      badge: p.reliability?.badge ?? null,
      notInView:
        p.stock_status === "NOT_IN_VIEW" && p.not_in_view
          ? { since: p.not_in_view.since, lastUnits: p.not_in_view.last_units, lastAt: p.not_in_view.last_at }
          : null,
    }))
    .sort(
      (a, b) =>
        ATTENTION[a.status] - ATTENTION[b.status] || shownUnits(a) - shownUnits(b) || a.name.localeCompare(b.name)
    );
}

export interface ShelfNowSummary {
  products: number;
  units: number;
  out: number;
  low: number;
  /** Products whose place is not in view; their last readings are in no total. */
  notInView: number;
}

export function shelfNowSummary(rows: ShelfNowRow[]): ShelfNowSummary {
  return {
    products: rows.length,
    units: rows.reduce((sum, r) => sum + shownUnits(r), 0),
    out: rows.filter((r) => r.status === "OOS").length,
    low: rows.filter((r) => r.status === "LOW").length,
    notInView: rows.filter((r) => r.status === "NOT_IN_VIEW").length,
  };
}

const STATUS_LABELS = { OOS: "Out of stock", LOW: "Low", IN_STOCK: "In stock", NOT_IN_VIEW: "Not in view" } as const;

export function stockStatusLabel(status: StockStatus): "Out of stock" | "Low" | "In stock" | "Not in view" {
  return STATUS_LABELS[status];
}

const ICT_OFFSET_MS = 7 * 3_600_000;

/** "15:45" for a time of the same UTC+7 day as now, "15:45 on 26/11" for an older one. Times are as the API
 * writes them (ISO, UTC+7). */
function clockText(at: string, now: Date): string {
  const time = at.slice(11, 16);
  const today = new Date(now.getTime() + ICT_OFFSET_MS).toISOString().slice(0, 10);
  if (at.slice(0, 10) === today) return time;
  return `${time} on ${at.slice(8, 10)}/${at.slice(5, 7)}`;
}

/** "Updated at 15:45" for a reading of the same UTC+7 day as now, "Updated at 15:45 on 26/11" for an older one.
 * asOf is a capture time as the API writes it (ISO, UTC+7). */
export function updatedText(asOf: string | null | undefined, now: Date): string | null {
  if (!asOf || asOf.length < 16) return null;
  return `Updated at ${clockText(asOf, now)}`;
}

/** "since 12:15 · last seen 6 at 12:10", "since 12:15 · was out of stock at 12:10", or just "since 12:15" when
 * nothing was seen there before. */
export function notInViewText(view: NotInView, now: Date): string {
  const since = `since ${clockText(view.since, now)}`;
  if (view.lastUnits === null || !view.lastAt) return since;
  const at = clockText(view.lastAt, now);
  return view.lastUnits === 0 ? `${since} · was out of stock at ${at}` : `${since} · last seen ${view.lastUnits} at ${at}`;
}

/** "Slide Cheese 145g", "A and B", "A, B and 2 more"; "" for none. */
export function namesText(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names[0]}, ${names[1]} and ${names.length - 2} more`;
}

/** Category lists the plan's products first; the others go in a section of their own. */
export function splitByPlan<T extends { inShelfPlan: boolean }>(items: T[]): { onPlan: T[]; offPlan: T[] } {
  return { onPlan: items.filter((i) => i.inShelfPlan), offPlan: items.filter((i) => !i.inShelfPlan) };
}

/** Outline colours that stay readable on a shelf photo; a ninth product starts over at the first. */
export const FRAME_COLORS = ["#FF4000", "#00C2FF", "#FFD400", "#7CFF00", "#FF4FD8", "#FFFFFF", "#9B6BFF", "#00FFB3"];

export interface FrameLegendItem {
  name: string;
  count: number;
  color: string;
  boxes: Box[];
}

/** One legend entry per product that has boxes in the frame, coloured in order from FRAME_COLORS. */
export function frameLegend(products: { sku_name: string; boxes: Box[] }[]): FrameLegendItem[] {
  return products
    .filter((p) => p.boxes.length > 0)
    .map((p, i) => ({ name: p.sku_name, count: p.boxes.length, color: FRAME_COLORS[i % FRAME_COLORS.length], boxes: p.boxes }));
}
