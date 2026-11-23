/**
 * Labels and number formats of the Model page. The 12 KPIs and their pilot targets are Datagent's
 * ("Validation - Accuracy Report", part B); values come from GET /model/summary.
 */

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
