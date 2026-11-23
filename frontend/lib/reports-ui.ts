// Types, filter labels and helpers for the Reports page.
// Numbers come only from the live API (GET /kpi, GET /reports/series). A value the backend does not
// compute yet stays null and the page shows "—"; nothing here is shelf data.

import type { ApiKpiResponse, ApiReportsSeriesPoint } from "./api";

// /kpi covers every capture the backend keeps, every category and every store, so these are the only
// honest filter choices until the API accepts filters.
export type TimeframeOption = "All-time";
export type CategoryOption = "All Categories";
export const TIMEFRAME_OPTIONS: TimeframeOption[] = ["All-time"];
export const CATEGORY_OPTIONS: CategoryOption[] = ["All Categories"];
export const ALL_STORES_LABEL = "All Stores";

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
  accuracySparkline: SparklinePoint[];
  restockSparkline: SparklinePoint[];
}

/** KPI cards from GET /kpi; null (shown as "—") where the backend has no value yet. */
export function kpisFromApi(kpi: ApiKpiResponse | null): KpiMetrics {
  return {
    activeStores: kpi ? kpi.active_stores_monitored : null,
    totalStores: kpi ? kpi.total_stores : null,
    totalOnShelfUnits: kpi ? kpi.total_on_shelf_units : null,
    avgInferenceTime:
      kpi && kpi.avg_processing_time_ms > 0 ? `${kpi.avg_processing_time_ms} ms` : null,
    osaPercent: null, // the backend does not compute OSA yet
    top50SkuAccuracy: kpi?.top_50_sku_accuracy?.value ?? null, // null until frames are labelled
    restockRateDelta: null, // the backend does not compute restock rate yet
    accuracySparkline: [],
    restockSparkline: [],
  };
}

export type ChartGranularity = "Day" | "Week" | "Month";
export const GRANULARITY_OPTIONS: ChartGranularity[] = ["Day", "Week", "Month"];

/** One bar of the shelf stock chart: captures of one day, ISO week or month, from GET /reports/series. */
export interface StockPoint {
  key: string;
  label: string;
  dateLabel: string;
  value: number; // average units found per capture, weighted by captures
  maxUnits: number;
  captures: number;
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
  const buckets = new Map<string, { meta: Pick<StockPoint, "key" | "label" | "dateLabel">; units: number; captures: number; max: number }>();
  for (const day of series) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) || day.captures <= 0) continue;
    const meta = bucketOf(day.date, granularity);
    const b = buckets.get(meta.key) ?? { meta, units: 0, captures: 0, max: 0 };
    b.units += day.avg_units * day.captures;
    b.captures += day.captures;
    b.max = Math.max(b.max, day.max_units);
    buckets.set(meta.key, b);
  }
  const ordered = [...buckets.values()].sort((a, b) => a.meta.key.localeCompare(b.meta.key));
  let previous: number | null = null;
  return ordered.map((b) => {
    const value = Math.round((b.units / b.captures) * 10) / 10;
    let vsLastPeriod: string | null = null;
    if (previous !== null && previous > 0) {
      const pct = ((value - previous) / previous) * 100;
      vsLastPeriod = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
    }
    const point: StockPoint = {
      ...b.meta,
      value,
      maxUnits: b.max,
      captures: b.captures,
      vsLastPeriod,
      isPositive: previous === null || value >= previous,
    };
    previous = value;
    return point;
  });
}

export type TrendMetricKey = "totalStock" | "oos" | "accuracy" | "restockVolume";

export type ActivityStatus = "OOS" | "RESTOCKED" | "DEPLETED" | "LOW STOCK";

export interface ShelfActivity {
  id: string;
  status: ActivityStatus;
  productName: string;
  timeAgo: string;
  storeName: string;
  storeDistrict: string;
  category: string;
  deltaText: string;
}
