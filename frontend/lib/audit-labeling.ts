/**
 * Labelling one frame on the Model page: what a click on a box does, the per-SKU totals shown beside the
 * image, when Save is allowed and what it sends. Verdicts follow the spec
 * (docs/superpowers/specs/2026-11-23-model-quality-page-design.md, section 5):
 *   correct      named box: one unit of that SKU; UNRECOGNIZED box: goods outside the catalogue
 *   wrong_sku    one unit of another catalogue SKU (trueSku)
 *   not_product  not a catalogue SKU (named box) / not goods at all (UNRECOGNIZED box)
 *   out_of_scope a real unit that the labelling rule does not count; the box is dropped from every number
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
// a ? box of a review frame (needs_flavour) has no suggestion to call right: pick its flavour, or say what it is not
const CYCLE_NEEDS_FLAVOUR: (Verdict | null)[] = [null, "wrong_sku", "not_product", "out_of_scope"];

/** The verdict after one more click on a box: unlabelled → correct → wrong SKU → not our SKU → out of scope →
 * unlabelled; a box that needs a flavour skips correct. */
export function nextVerdict(verdict: Verdict | null, needsFlavour = false): Verdict | null {
  const cycle = needsFlavour ? CYCLE_NEEDS_FLAVOUR : CYCLE;
  return cycle[(cycle.indexOf(verdict) + 1) % cycle.length];
}

const QUEUE_RANK: Record<string, number> = { scoring: 0, training: 1, review: 2 };

/** The order "Label frames" opens pending frames in: scoring, then training, then review frames, each oldest first. */
export function labelQueueOrder(
  items: Pick<ApiAuditListItem, "audit_id" | "purpose" | "capture_timestamp">[]
): string[] {
  return [...items]
    .sort(
      (a, b) =>
        (QUEUE_RANK[a.purpose] ?? 3) - (QUEUE_RANK[b.purpose] ?? 3) ||
        a.capture_timestamp.localeCompare(b.capture_timestamp)
    )
    .map((a) => a.audit_id);
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

/** The labelling rule a save stores (backend LABEL_RULE). A (24/11): Slide cans on the display's top tray.
 * B (25/11): every unit of the store's shelf plan whose face, lid or top shows, so the TH packs too. */
export const CURRENT_LABEL_RULE = "B";

/** The frames "Relabel them" opens in the labeller: done scoring frames labelled under an older rule (label_rule is
 * not CURRENT_LABEL_RULE), oldest first. GET /model/audits?old_rule=1 lists only these; the filter keeps the labeller
 * to them anyway. The labeller loads each frame's saved verdicts, and Save stores it under the current rule. */
export function relabelQueue(items: RelabelCandidate[]): string[] {
  return items
    .filter((a) => a.status === "done" && a.purpose === "scoring" && a.label_rule !== CURRENT_LABEL_RULE)
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

// --- Faster labelling: number keys, one button for the boxes that are right, and moving to the next box ---

/** A box as the labeller lists it: a ? box (needs_flavour) has no suggestion to call right. */
export interface LabelBox extends AuditBox {
  needs_flavour?: boolean;
}

const VERDICT_KEYS: Record<string, Verdict> = { "1": "correct", "2": "wrong_sku", "3": "not_product", "4": "out_of_scope" };

/** The verdict a key gives the highlighted box: 1 Right, 2 Wrong SKU, 3 Not our SKU, 4 Out of scope; null for any
 * other key, and for 1 on a ? box. */
export function verdictForKey(key: string, needsFlavour = false): Verdict | null {
  const verdict = VERDICT_KEYS[key] ?? null;
  return needsFlavour && verdict === "correct" ? null : verdict;
}

const unjudgedWithSuggestion = (box: LabelBox, labels: Record<number, BoxLabel>) =>
  !box.needs_flavour && !labels[box.box_id]?.verdict;

/** How many boxes "mark the rest right" would mark: unjudged boxes that have a suggestion. */
export function restCount(aiBoxes: LabelBox[], labels: Record<number, BoxLabel>): number {
  return aiBoxes.filter((box) => unjudgedWithSuggestion(box, labels)).length;
}

/** The labels with those boxes marked right; judged boxes and ? boxes are left as they are. */
export function markRestCorrect(aiBoxes: LabelBox[], labels: Record<number, BoxLabel>): Record<number, BoxLabel> {
  const next = { ...labels };
  for (const box of aiBoxes) {
    if (unjudgedWithSuggestion(box, labels)) next[box.box_id] = { verdict: "correct", trueSku: null };
  }
  return next;
}

/** The next box without a verdict after box `after` in list order, wrapping round; null when all are judged. */
export function nextUnjudged(
  aiBoxes: AuditBox[],
  labels: Record<number, BoxLabel>,
  after: number | null
): number | null {
  const start = after === null ? -1 : aiBoxes.findIndex((box) => box.box_id === after);
  for (let step = 1; step <= aiBoxes.length; step++) {
    const box = aiBoxes[(start + step) % aiBoxes.length];
    if (!labels[box.box_id]?.verdict) return box.box_id;
  }
  return null;
}
