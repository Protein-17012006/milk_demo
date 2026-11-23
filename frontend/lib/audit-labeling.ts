/**
 * Labelling one frame on the Model page: what a click on a box does, the per-SKU totals shown beside the
 * image, when Save is allowed and what it sends. Verdicts follow the spec
 * (docs/superpowers/specs/2026-11-23-model-quality-page-design.md, section 5):
 *   correct      named box: one unit of that SKU; UNRECOGNIZED box: goods outside the catalogue
 *   wrong_sku    one unit of another catalogue SKU (trueSku)
 *   not_product  not a catalogue SKU (named box) / not goods at all (UNRECOGNIZED box)
 */

export type Verdict = "correct" | "wrong_sku" | "not_product";

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

const CYCLE: (Verdict | null)[] = [null, "correct", "wrong_sku", "not_product"];

/** The verdict after one more click on a box: unlabelled → correct → wrong SKU → not a product → unlabelled. */
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
    if (box.sku_id) bump(box.sku_id, "model");
    const label = labels[box.box_id];
    if (!label) continue;
    if (label.verdict === "correct" && box.sku_id) bump(box.sku_id, "truth");
    else if (label.verdict === "wrong_sku" && label.trueSku) bump(label.trueSku, "truth");
  }
  for (const point of missed) bump(point.sku_id, "truth");
  return out;
}

/** Save needs a verdict on every box, and the right SKU on every box marked wrong. */
export function canSave(aiBoxes: AuditBox[], labels: Record<number, BoxLabel>): boolean {
  return aiBoxes.every((box) => {
    const label = labels[box.box_id];
    if (!label?.verdict) return false;
    return label.verdict !== "wrong_sku" || Boolean(label.trueSku);
  });
}

/** Body of PUT /model/audits/{id}: verdicts by box, missed points rounded to whole frame pixels. */
export function toPayload(
  labels: Record<number, BoxLabel>,
  missed: MissedPoint[]
): {
  verdicts: { box_id: number; verdict: Verdict; true_sku_id?: string }[];
  missed: MissedPoint[];
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
  };
}
