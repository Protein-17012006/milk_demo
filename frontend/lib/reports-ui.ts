// Types, filter labels and helpers for the Reports (Dashboard) page.
// Numbers come only from the live API (GET /kpi, /reports/series, /reports/trends, /shelf-events). A value the
// backend cannot give stays null and the page shows "—" with the reason; nothing here is shelf data.

import type { ApiKpiResponse, ApiReportsSeriesPoint } from "./api";
import { DEFAULT_DAYS, TIMEFRAMES, pctChange } from "./shelf-ui";

export type TimeframeOption = string;
export type CategoryOption = "All Categories" | "Milk" | "Snacks";
export const TIMEFRAME_OPTIONS: TimeframeOption[] = TIMEFRAMES.map((t) => t.label);
export const DEFAULT_TIMEFRAME: TimeframeOption =
  TIMEFRAMES.find((t) => t.days === DEFAULT_DAYS)?.label ?? TIMEFRAME_OPTIONS[0];
export const CATEGORY_OPTIONS: CategoryOption[] = ["All Categories", "Milk", "Snacks"];
export const ALL_STORES_LABEL = "All Stores";

/** Days of a Timeframe label. */
export const daysOf = (label: TimeframeOption) => TIMEFRAMES.find((t) => t.label === label)?.days ?? DEFAULT_DAYS;

/** The SKU master category to send, or undefined for every category. */
export const categoryParam = (c: CategoryOption) => (c === "All Categories" ? undefined : c);

/** "DEMO-S01 — Demo Store S01" → "DEMO-S01"; the "All Stores (n)" label → undefined. */
export const storeParam = (label: string) => (label.startsWith(ALL_STORES_LABEL) ? undefined : label.split(" — ")[0]);

export interface SparklinePoint {
  idx: number;
  value: number;
}

export interface KpiMetrics {
  activeStores: number | null;
  totalStores: number | null;
  totalOnShelfUnits: number | null;
  avgInferenceTime: string | null;
  osaPercent: number | null;
  top50SkuAccuracy: number | null;
  restockRateDelta: string | null;
}

const percentOf = (share: number | null | undefined) =>
  share === null || share === undefined ? null : Math.round(share * 1000) / 10;

/** KPI cards from GET /kpi; null (shown as "—") where the backend has no value. */
export function kpisFromApi(kpi: ApiKpiResponse | null): KpiMetrics {
  return {
    activeStores: kpi ? kpi.active_stores_monitored : null,
    totalStores: kpi ? kpi.total_stores : null,
    totalOnShelfUnits: kpi ? kpi.total_on_shelf_units : null,
    avgInferenceTime:
      kpi && kpi.avg_processing_time_ms > 0 ? `${kpi.avg_processing_time_ms} ms` : null,
    osaPercent: percentOf(kpi?.osa?.value),
    top50SkuAccuracy: percentOf(kpi?.top_50_sku_accuracy?.value),
    restockRateDelta: pctChange(kpi?.restock_rate?.change_pct ?? null),
  };
}

export type ChartGranularity = "Day" | "Week" | "Month";
export const GRANULARITY_OPTIONS: ChartGranularity[] = ["Day", "Week", "Month"];

/** One bar of the shelf stock chart: one day, ISO week or month of counted checks, from GET /reports/series. */
export interface StockPoint {
  key: string;
  label: string;
  dateLabel: string;
  value: number; // average units of the expected SKUs per check, weighted by checks
  maxUnits: number;
  checks: number;
  vsLastPeriod: string | null; // change against the previous bar; null for the first bar
  isPositive: boolean;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** ISO-8601 week of a YYYY-MM-DD date: [week-year, week number]. */
function isoWeek(date: string): [number, number] {
  const [y, m, d] = date.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  const weekday = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - weekday);
  const yearStart = Date.UTC(t.getUTCFullYear(), 0, 1);
  return [t.getUTCFullYear(), Math.ceil(((t.getTime() - yearStart) / 86_400_000 + 1) / 7)];
}

function bucketOf(date: string, granularity: ChartGranularity): Pick<StockPoint, "key" | "label" | "dateLabel"> {
  const [y, m, d] = date.split("-");
  if (granularity === "Day") {
    return { key: date, label: `${d}/${m}`, dateLabel: `${d}/${m}/${y}` };
  }
  if (granularity === "Month") {
    const name = MONTHS[Number(m) - 1];
    return { key: `${y}-${m}`, label: name.toUpperCase(), dateLabel: `${name} ${y}` };
  }
  const [wy, w] = isoWeek(date);
  const ww = String(w).padStart(2, "0");
  return { key: `${wy}-W${ww}`, label: `W${ww}`, dateLabel: `Week ${w}, ${wy}` };
}

export function bucketStockSeries(
  series: ApiReportsSeriesPoint[],
  granularity: ChartGranularity
): StockPoint[] {
  const buckets = new Map<string, { meta: Pick<StockPoint, "key" | "label" | "dateLabel">; units: number; checks: number; max: number }>();
  for (const day of series) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) || day.checks <= 0) continue;
    const meta = bucketOf(day.date, granularity);
    const b = buckets.get(meta.key) ?? { meta, units: 0, checks: 0, max: 0 };
    b.units += day.avg_units * day.checks;
    b.checks += day.checks;
    b.max = Math.max(b.max, day.max_units);
    buckets.set(meta.key, b);
  }
  const ordered = [...buckets.values()].sort((a, b) => a.meta.key.localeCompare(b.meta.key));
  let previous: number | null = null;
  return ordered.map((b) => {
    const value = Math.round((b.units / b.checks) * 10) / 10;
    let vsLastPeriod: string | null = null;
    if (previous !== null && previous > 0) {
      const pct = ((value - previous) / previous) * 100;
      vsLastPeriod = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
    }
    const point: StockPoint = {
      ...b.meta,
      value,
      maxUnits: b.max,
      checks: b.checks,
      vsLastPeriod,
      isPositive: previous === null || value >= previous,
    };
    previous = value;
    return point;
  });
}

export type TrendMetricKey = "totalStock" | "oos" | "accuracy" | "restockVolume";
