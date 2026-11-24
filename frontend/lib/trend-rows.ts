// How the trend chart turns API points into rows. A separate file with no runtime imports so node can test it.
import type { ApiTrendPoint } from "./api";

/** "2026-11-27" → "27/11"; "20261128-09" → "09h". */
const pointLabel = (t: string) => (t.includes("-") && t.length === 10 ? `${t.slice(8, 10)}/${t.slice(5, 7)}` : `${t.slice(9, 11)}h`);

/** Rows for the trend chart. A point with no value stays null (never 0), so the line breaks there; a share from
 * the API (0.644) is drawn as a percent (64.4). */
export function trendRows(points: ApiTrendPoint[], unit?: string): { label: string; value: number | null }[] {
  return points.map((p) => ({
    label: pointLabel(p.t),
    value: p.value === null ? null : unit === "%" ? Math.round(p.value * 1000) / 10 : p.value,
  }));
}
