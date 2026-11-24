/**
 * Labels and number formats of the Model page. The 12 KPIs and their pilot targets are Datagent's
 * ("Validation - Accuracy Report", part B); values come from GET /model/summary. Intervals are 95%, from resampling
 * whole labelled frames (docs/superpowers/specs/2026-11-24-reliability-design.md, 1.2c).
 */

import type { ApiCheckLevel, ApiDisplayCheck, ApiInterval, ApiPeriodSku, ApiStat, DayPeriod } from "./api";

export interface KpiValue {
  value: number | null;
  target: [string, number];
  met: boolean | null;
  n: number;
}

export const KPI_ORDER: { name: string; label: string; hint: string }[] = [
  { name: "sku_identification_accuracy", label: "SKU identification (top 50)", hint: "Boxes named with the right SKU, top 50 SKUs by volume" },
  { name: "overall_identification_accuracy", label: "Identification, all SKUs", hint: "Boxes named with the right SKU" },
  { name: "unit_count_mae", label: "Count error (MAE)", hint: "Mean units off per SKU per frame" },
  { name: "unit_count_accuracy_avg", label: "Count accuracy", hint: "Average closeness of the count to the truth" },
  { name: "exact_match_rate", label: "Exact match", hint: "SKU rows counted exactly and named right" },
  { name: "minor_error_rate", label: "Minor error (1–2)", hint: "SKU rows off by 1–2 units; target is exact + minor" },
  { name: "missed_sku_rate", label: "Missed SKU", hint: "SKUs on the shelf the model did not report" },
  { name: "false_detection_rate", label: "False detection", hint: "Boxes on something that is not one of our SKUs" },
  { name: "avg_confidence_correct", label: "Confidence when right", hint: "Average score of boxes named right" },
  { name: "avg_confidence_incorrect", label: "Confidence when wrong", hint: "Average score of wrong boxes (the model should doubt them)" },
  { name: "avg_processing_time_ms", label: "Processing time", hint: "Model time per frame" },
  { name: "unrecognized_product_rate", label: "Unrecognized", hint: "Boxes the model could not name" },
];

const PERCENT = new Set([
  "sku_identification_accuracy",
  "overall_identification_accuracy",
  "unit_count_accuracy_avg",
  "exact_match_rate",
  "minor_error_rate",
  "missed_sku_rate",
  "false_detection_rate",
  "unrecognized_product_rate",
]);

const OPS: Record<string, string> = { ">=": "≥", "<=": "≤", ">": ">", "<": "<" };

export type Tone = "met" | "missed" | "none";

/** One KPI as text: "—" when there are no samples (never 0), its target, and whether it meets the target. */
export function kpiDisplay(name: string, kpi: KpiValue): { text: string; targetText: string; tone: Tone } {
  const [op, threshold] = kpi.target;
  let value: (v: number) => string;
  let target: (v: number) => string;
  if (PERCENT.has(name)) {
    value = (v) => `${(v * 100).toFixed(1)}%`;
    target = (v) => `${Math.round(v * 100)}%`;
  } else if (name === "avg_processing_time_ms") {
    value = (v) => `${Math.round(v)} ms`;
    target = (v) => `${v} ms`;
  } else {
    value = (v) => v.toFixed(2);
    target = (v) => `${v}`;
  }
  return {
    text: kpi.value === null ? "—" : value(kpi.value),
    targetText: `${OPS[op] ?? op} ${target(threshold)}`,
    tone: kpi.met === null ? "none" : kpi.met ? "met" : "missed",
  };
}

/** A share 0..1 as "12.5%", or "—". */
export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
}

/** How a number reads: a share, a plain count or score, or a signed mean (model minus truth). */
export type Unit = "percent" | "number" | "signed";

const MINUS = "−";

/** "1 frame", "3 frames". */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** A signed mean with one decimal and the site's minus sign: "+0.7", "−2.0"; "0.0" has no sign; "—" without one. */
export function signedText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const text = Math.abs(value).toFixed(1);
  return Number(text) === 0 ? text : `${value < 0 ? MINUS : "+"}${text}`;
}

function valueText(value: number, unit: Unit): string {
  return unit === "percent" ? pct(value) : unit === "signed" ? signedText(value) : value.toFixed(2);
}

function rangeText([lo, hi]: [number, number], unit: Unit): string {
  if (unit === "percent") return `${Math.round(lo * 100)}–${Math.round(hi * 100)}%`;
  if (unit === "signed") return `${signedText(lo)} to ${signedText(hi)}`;
  return `${lo.toFixed(2)}–${hi.toFixed(2)}`;
}

/** A 95% interval: "(75–83%)" for shares, "(0.50–0.83)" for counts and scores, "(−3.0 to +1.0)" for signed means;
 * "" without one (under 2 frames). */
export function ciText(ci: ApiInterval | undefined, unit: Unit = "percent"): string {
  return ci ? `(${rangeText(ci, unit)})` : "";
}

/** The interval under a KPI, in the KPI's unit; "" when it has none (processing time, under 2 frames). */
export function kpiCiText(name: string, ci: ApiInterval | undefined): string {
  return ciText(ci, PERCENT.has(name) ? "percent" : "number");
}

/** A ratio over frames in two parts, the value and the detail: "78.7%" and "(75–83%, n = 11 frames)". Without a
 * value: "Not enough samples" and "(n = 0)", never 0%. one/many name what n counts. */
export function statParts(s: ApiStat, unit: Unit = "percent", one = "", many = `${one}s`): { text: string; detail: string } {
  const n = `n = ${one ? plural(s.n, one, many) : s.n}`;
  if (s.value === null) return { text: "Not enough samples", detail: `(${n})` };
  return { text: valueText(s.value, unit), detail: s.ci ? `(${rangeText(s.ci, unit)}, ${n})` : `(${n})` };
}

/** statParts as one phrase: "78.7% (75–83%, n = 11 frames)", "Not enough samples (n = 0 SKU rows)". */
export function statText(s: ApiStat, unit: Unit = "percent", one = "", many = `${one}s`): string {
  const { text, detail } = statParts(s, unit, one, many);
  return `${text} ${detail}`;
}

/** Why a SKU's numbers are not shown: "Not enough samples (n = 3 frames · 7 cans · 1 day)", or "(n = 0 frames)"
 * when no frame had one. A SKU needs 10 frames with a true can, 20 true cans, and those frames on 2 days or more. */
export function notEnoughText(s: { frames?: number; true_units: number; days?: number }): string {
  const frames = s.frames ?? 0;
  if (frames === 0) return "Not enough samples (n = 0 frames)";
  const parts = [plural(frames, "frame"), plural(s.true_units, "can"), plural(s.days ?? 0, "day")];
  return `Not enough samples (n = ${parts.join(" · ")})`;
}

export const PERIODS: { key: DayPeriod; label: string; hours: string }[] = [
  { key: "morning", label: "Morning", hours: "before 12:00" },
  { key: "afternoon", label: "Afternoon", hours: "12:00–17:00" },
  { key: "evening", label: "Evening", hours: "from 17:00" },
];

/** One SKU at one time of day: "found right 80.0% · named right 90.0%", or why there are not enough samples. */
export function periodCellText(cell: ApiPeriodSku | undefined): string {
  if (!cell) return notEnoughText({ frames: 0, true_units: 0, days: 0 });
  if (!cell.enough) return notEnoughText(cell);
  return `found right ${pct(cell.found_right)} · named right ${pct(cell.named_right)}`;
}

export const PER_SKU_NOTE =
  "Named right: of the boxes the model gave this SKU, the share that were it. Found right: of the cans of it really " +
  "there, the share the model named right. Bias / frame: cans counted minus cans there, per frame (+ is too many). " +
  "Under each number, its 95% interval.";

export const PERIOD_NOTE =
  "Hours in UTC+7. Errors change with the light and with how the display is packed, so each time of day is scored " +
  "on its own.";

export const PRESENCE_INFO = {
  what:
    "Each labelled frame gives one row per SKU: the SKUs the store must carry (its shelf plan) and any SKU the " +
    "model or the labeller counted. A row asks one thing: is the SKU on the shelf?",
  read:
    "Agree should be near 100%. A false empty is what becomes an out-of-stock alert that is not real; a missed " +
    "empty is an out-of-stock the Dashboard does not see. The last line asks the same of the 5-minute checks the " +
    "Dashboard uses.",
};

export const PRESENCE: { key: "agree" | "false_empty" | "missed_empty"; label: string; hint: string }[] = [
  {
    key: "agree",
    label: "Agree",
    hint: "SKU rows where the model and the labeller both say the SKU is there, or both say it is not.",
  },
  {
    key: "false_empty",
    label: "False empty",
    hint: "Of the rows the model called empty, those where cans were there: an out-of-stock that is not real.",
  },
  {
    key: "missed_empty",
    label: "Missed empty",
    hint: "Of the rows that were really empty, those where the model still counted cans: an out-of-stock missed.",
  },
];

/** "Dashboard checks (2 frames): cans per SKU off by −0.7 (−1.0 to −0.3, n = 6 SKU rows) · present or absent agree
 * 87.5% (75–100%, n = 8 SKU rows)": the 5-minute numbers the Dashboard uses against the labelled frames. */
export function checkLevelText(c: ApiCheckLevel): string {
  if (c.frames === 0) return "Dashboard checks: Not enough samples (n = 0 frames)";
  const off = statText(c.count_bias, "signed", "SKU row");
  const agree = statText(c.presence_agree, "percent", "SKU row");
  return `Dashboard checks (${plural(c.frames, "frame")}): cans per SKU off by ${off} · present or absent agree ${agree}`;
}

/** 'Display check: matched the labellers on 66.7% (33–100%, n = 3 scoring frames) · wrongly "not in view" 1 ·
 * wrongly "in view" 0'. */
export function displayCheckText(d: ApiDisplayCheck): string {
  const agree = statText(d.agree, "percent", "scoring frame");
  if (d.agree.value === null) return `Display check: ${agree}`;
  return `Display check: matched the labellers on ${agree} · wrongly "not in view" ${d.false_not_visible} · wrongly "in view" ${d.false_visible}`;
}
