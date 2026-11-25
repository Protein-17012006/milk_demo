/**
 * The Model page's Live health block: what each hourly number means, and its chart data. The numbers come from
 * GET /model/health, worked out per camera-hour by backend/model_health.py from the captures.
 */

import type { ApiModelHealthItem } from "./api";

export type HealthMetric = "conf_median" | "flagged_row_pct" | "jitter" | "processing_ms_median" | "captures";

export interface HealthMetricInfo {
  key: HealthMetric;
  label: string;
  /** What the number measures. */
  what: string;
  /** Which way is good, what is normal, and what a change usually means. */
  read: string;
  /** Shares (0..1 from the API) are drawn and shown as percentages. */
  percent?: boolean;
  /** A line drawn across the chart, in chart units. */
  reference?: { value: number; label: string };
  format: (v: number) => string;
}

export const HEALTH_METRICS: HealthMetricInfo[] = [
  {
    key: "conf_median",
    label: "Median confidence",
    what: "How sure the model is about the boxes it draws: the middle score of every box found that hour, from 0 to 1.",
    read:
      "Higher is better. A reading under 0.70 is flagged for a person to check (dashed line). A sudden fall usually " +
      "means the view changed: lights off, glare, something in front of the shelf, or goods the model was not trained on.",
    reference: { value: 0.7, label: "Flag threshold 0.70" },
    format: (v) => v.toFixed(2),
  },
  {
    key: "flagged_row_pct",
    label: "Flagged readings",
    what:
      "Share of readings flagged that hour. A reading is one SKU in one capture; it is flagged when its confidence " +
      "is under 0.70 or its boxes matched no SKU.",
    read:
      "Lower is better. Flagged readings go to the review queue on Products. Near 100% means the model doubts almost " +
      "everything it sees, as when the light is off or the shelf holds goods it does not know.",
    percent: true,
    format: (v) => `${Math.round(v)}%`,
  },
  {
    key: "jitter",
    label: "Count jumps",
    what:
      "How much the count moves between two captures in a row: units that appeared or disappeared, added up over all " +
      "SKUs and averaged over the hour.",
    read:
      "Lower is steadier. On a shelf nobody touches it stays near 0. It rises when shoppers or staff move goods, or " +
      "when the model sees an item in one capture and misses it in the next.",
    format: (v) => `${v.toFixed(1)} units`,
  },
  {
    key: "processing_ms_median",
    label: "ms per frame",
    what: "Time the model takes to count one capture, in milliseconds (the hour's median).",
    read:
      "Lower is faster. Datagent's limit is 30 000 ms per image (KPI 11); a few hundred ms is normal on the GPU " +
      "machine. A rise means the machine is busy or slower.",
    format: (v) => `${Math.round(v)} ms`,
  },
  {
    key: "captures",
    label: "Captures per hour",
    what: "How many captures were counted and saved that hour.",
    read:
      "Shows that the camera, the stream and the counter were running. The number follows the counting schedule, so " +
      "compare an hour with the hours around it. A gap in the line means nothing was counted then.",
    format: (v) => String(Math.round(v)),
  },
];

/** The Display check line of Live health (numbers from GET /model/summary, display_check). */
export const DISPLAY_CHECK_INFO = {
  what:
    'Whether the worker\'s display check agreed with the labellers on the scoring frames: a labelled frame had the ' +
    'display in view, a frame skipped as "Display not in view" did not. Only frames the check judged count: frames ' +
    "from before the check, or from before the worker had learnt the display, are left out.",
  read:
    'Wrongly "not in view" drops 5-minute checks the Dashboard could have counted; wrongly "in view" lets an empty ' +
    "space be counted as out of stock.",
};

const INFO = new Map(HEALTH_METRICS.map((m) => [m.key, m]));
const HOUR = /^(\d{4})(\d{2})(\d{2})-(\d{2})$/;
const HOUR_MS = 3_600_000;

/** "20261123-22" (UTC+7) as "23/11 22h". */
export const hourLabel = (hour: string) => `${hour.slice(6, 8)}/${hour.slice(4, 6)} ${hour.slice(9, 11)}h`;

// Hours are UTC+7 wall-clock hours; they are stepped as UTC to stay clear of the browser's time zone.
function hourTime(hour: string): number | null {
  const m = HOUR.exec(hour);
  return m ? Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4])) : null;
}

function hourOf(time: number): string {
  const d = new Date(time);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}-${p(d.getUTCHours())}`;
}

function chartValue(item: ApiModelHealthItem, metric: HealthMetric): number | null {
  const raw = item[metric];
  if (raw === undefined || raw === null) return null;
  return INFO.get(metric)?.percent ? raw * 100 : raw;
}

export type HealthRow = Record<string, string | number | null>;

/**
 * One row per hour, from the first to the last hour with data, and one value per camera. Hours without captures
 * stay null, so the line breaks there instead of joining hours that are far apart.
 */
export function healthChart(items: ApiModelHealthItem[], metric: HealthMetric): { cameras: string[]; rows: HealthRow[] } {
  const timed = items.filter((i) => hourTime(i.hour) !== null);
  if (timed.length === 0) return { cameras: [], rows: [] };
  const cameras = [...new Set(timed.map((i) => i.camera_id))].sort();
  const byCameraHour = new Map(timed.map((i) => [`${i.camera_id}|${i.hour}`, i]));
  const times = timed.map((i) => hourTime(i.hour) as number);
  const rows: HealthRow[] = [];
  for (let t = Math.min(...times); t <= Math.max(...times); t += HOUR_MS) {
    const hour = hourOf(t);
    const row: HealthRow = { hour, label: hourLabel(hour) };
    for (const camera of cameras) {
      const item = byCameraHour.get(`${camera}|${hour}`);
      row[camera] = item ? chartValue(item, metric) : null;
    }
    rows.push(row);
  }
  return { cameras, rows };
}

/** Per camera, the value of the last hour that has one (in chart units). */
export function latestHealth(
  items: ApiModelHealthItem[],
  metric: HealthMetric
): { camera: string; hour: string; label: string; value: number }[] {
  const latest = new Map<string, { hour: string; value: number }>();
  for (const item of items) {
    const value = chartValue(item, metric);
    if (value === null || hourTime(item.hour) === null) continue;
    const seen = latest.get(item.camera_id);
    if (!seen || item.hour > seen.hour) latest.set(item.camera_id, { hour: item.hour, value });
  }
  return [...latest.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([camera, { hour, value }]) => ({ camera, hour, label: hourLabel(hour), value }));
}

/** A value in chart units with its unit, or "—". */
export function formatHealth(metric: HealthMetric, value: number | null): string {
  const info = INFO.get(metric);
  return value === null || !info ? "—" : info.format(value);
}
