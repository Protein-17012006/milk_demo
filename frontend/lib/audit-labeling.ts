/**
 * Labelling one frame on the Model page: what a click on a box does, the per-SKU totals shown beside the
 * image, when Save is allowed and what it sends. Verdicts follow the spec
 * (docs/superpowers/specs/2026-11-23-model-quality-page-design.md, section 5):
 *   correct      named box: one unit of that SKU; UNRECOGNIZED box: goods outside the catalogue
 *   wrong_sku    one unit of another catalogue SKU (trueSku)
 *   not_product  not a catalogue SKU (named box) / not goods at all (UNRECOGNIZED box)
 *   out_of_scope a real can that rule A does not count; the box is dropped from every number
 */

import type { ApiAuditListItem } from "./api";

export type Verdict = "correct" | "wrong_sku" | "not_product" | "out_of_scope";

export interface BoxLabel {
  verdict: Verdict | null;
  trueSku: string | null;
}

export interface AuditBox {
  box_id: number;
  sku_id: string | null;
}

export interface MissedPoint {
  sku_id: string;
  x: number;
  y: number;
}

const CYCLE: (Verdict | null)[] = [null, "correct", "wrong_sku", "not_product", "out_of_scope"];

/** The verdict after one more click on a box: unlabelled → correct → wrong SKU → not our SKU → out of scope → unlabelled. */
export function nextVerdict(verdict: Verdict | null): Verdict | null {
  return CYCLE[(CYCLE.indexOf(verdict) + 1) % CYCLE.length];
}

/** Model units and true units per SKU (model label) for the labels given so far. */
export function totalsBySku(
  aiBoxes: AuditBox[],
  labels: Record<number, BoxLabel>,
  missed: { sku_id: string }[]
): Record<string, { model: number; truth: number }> {
  const out: Record<string, { model: number; truth: number }> = {};
  const bump = (sku: string, key: "model" | "truth") => {
    out[sku] ??= { model: 0, truth: 0 };
    out[sku][key] += 1;
  };
  for (const box of aiBoxes) {
    const label = labels[box.box_id];
    if (label?.verdict === "out_of_scope") continue; // counts neither for the model nor for the truth
    if (box.sku_id) bump(box.sku_id, "model");
    if (!label) continue;
    if (label.verdict === "correct" && box.sku_id) bump(box.sku_id, "truth");
    else if (label.verdict === "wrong_sku" && label.trueSku) bump(label.trueSku, "truth");
  }
  for (const point of missed) bump(point.sku_id, "truth");
  return out;
}

/** Save needs a verdict on every box, the right SKU on every box marked wrong, and the missed-cans check ticked. */
export function canSave(aiBoxes: AuditBox[], labels: Record<number, BoxLabel>, missesChecked: boolean): boolean {
  if (!missesChecked) return false;
  return aiBoxes.every((box) => {
    const label = labels[box.box_id];
    if (!label?.verdict) return false;
    return label.verdict !== "wrong_sku" || Boolean(label.trueSku);
  });
}

/** What relabelQueue reads of an item of GET /model/audits. */
export type RelabelCandidate = Pick<
  ApiAuditListItem,
  "audit_id" | "capture_timestamp" | "purpose" | "status" | "label_rule"
>;

/** The frames "Relabel them" opens in the labeller: done scoring frames labelled before rule A (label_rule is not
 * "A"), oldest first. GET /model/audits?old_rule=1 lists only these; the filter keeps the labeller to them anyway.
 * The labeller loads each frame's saved verdicts, and Save stores it under rule A. */
export function relabelQueue(items: RelabelCandidate[]): string[] {
  return items
    .filter((a) => a.status === "done" && a.purpose === "scoring" && a.label_rule !== "A")
    .sort((a, b) => a.capture_timestamp.localeCompare(b.capture_timestamp))
    .map((a) => a.audit_id);
}

/** Body of PUT /model/audits/{id}: verdicts by box, missed points rounded to whole frame pixels, check ticked. */
export function toPayload(
  labels: Record<number, BoxLabel>,
  missed: MissedPoint[]
): {
  verdicts: { box_id: number; verdict: Verdict; true_sku_id?: string }[];
  missed: MissedPoint[];
  misses_checked: true;
} {
  const verdicts = Object.entries(labels)
    .filter(([, label]) => label.verdict !== null)
    .map(([id, label]) => ({
      box_id: Number(id),
      verdict: label.verdict as Verdict,
      ...(label.verdict === "wrong_sku" && label.trueSku ? { true_sku_id: label.trueSku } : {}),
    }))
    .sort((a, b) => a.box_id - b.box_id);
  return {
    verdicts,
    missed: missed.map((p) => ({ sku_id: p.sku_id, x: Math.round(p.x), y: Math.round(p.y) })),
    misses_checked: true,
  };
}
