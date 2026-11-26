// What is on the shelf now, product by product: the rows of the Dashboard's table, their totals and labels, the
// line that says when the numbers were read, and the legend of the shelf photo.
// The numbers are the latest reading of each product (GET /products), the same ones the Category page lists. The
// backend says which products are on the shelf plan and how each one's stock stands; nothing here recomputes that.
// Imports are type-only so Node can run the unit tests without the Next.js path aliases.
import type { ReliabilityBadge } from "./api";
import type { Box } from "./frame-geometry";

export type StockStatus = "OOS" | "LOW" | "IN_STOCK";

/** The fields of a GET /products item the table reads; an older backend leaves out the plan and the status. */
export interface ShelfNowInput {
  sku_id: string;
  sku_name: string;
  image_url?: string | null;
  unit_count: number;
  in_shelf_plan?: boolean;
  stock_status?: StockStatus | null;
  reliability?: { badge: ReliabilityBadge } | null;
}

export interface ShelfNowRow {
  skuId: string;
  name: string;
  imageUrl: string | null;
  units: number;
  status: StockStatus;
  badge: ReliabilityBadge | null;
}

const ATTENTION: Record<StockStatus, number> = { OOS: 0, LOW: 1, IN_STOCK: 2 };

/** Products of the shelf plan: out of stock first, then low, then in stock; fewer units first; then by name. */
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
    }))
    .sort((a, b) => ATTENTION[a.status] - ATTENTION[b.status] || a.units - b.units || a.name.localeCompare(b.name));
}

export interface ShelfNowSummary {
  products: number;
  units: number;
  out: number;
  low: number;
}

export function shelfNowSummary(rows: ShelfNowRow[]): ShelfNowSummary {
  return {
    products: rows.length,
    units: rows.reduce((sum, r) => sum + r.units, 0),
    out: rows.filter((r) => r.status === "OOS").length,
    low: rows.filter((r) => r.status === "LOW").length,
  };
}

const STATUS_LABELS = { OOS: "Out of stock", LOW: "Low", IN_STOCK: "In stock" } as const;

export function stockStatusLabel(status: StockStatus): "Out of stock" | "Low" | "In stock" {
  return STATUS_LABELS[status];
}

const ICT_OFFSET_MS = 7 * 3_600_000;

/** "Updated at 15:45" for a reading of the same UTC+7 day as now, "Updated at 15:45 on 26/11" for an older one.
 * asOf is a capture time as the API writes it (ISO, UTC+7). */
export function updatedText(asOf: string | null | undefined, now: Date): string | null {
  if (!asOf || asOf.length < 16) return null;
  const time = asOf.slice(11, 16);
  const today = new Date(now.getTime() + ICT_OFFSET_MS).toISOString().slice(0, 10);
  if (asOf.slice(0, 10) === today) return `Updated at ${time}`;
  return `Updated at ${time} on ${asOf.slice(8, 10)}/${asOf.slice(5, 7)}`;
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
