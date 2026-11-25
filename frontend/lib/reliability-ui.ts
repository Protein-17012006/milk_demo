// Reliability badge of one SKU (High / Medium / Low / Not enough samples): labels, colours and the details text.
// The badge is worked out by the backend from the labelled scoring frames of the last 14 days
// (docs/superpowers/specs/2026-11-24-reliability-design.md, 1.3); this file only says it in words.

import type { ApiReliability, ReliabilityBadge } from "./api";

const LABELS: Record<ReliabilityBadge, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  insufficient: "Not enough samples",
};

/** Pill colours (background, text) per badge. */
export const BADGE_COLORS: Record<ReliabilityBadge, string> = {
  high: "bg-[#E8F5E9] text-[#2E7D32]",
  medium: "bg-[#FEF3C7] text-[#B45309]",
  low: "bg-[#FEE2E2] text-[#DC2626]",
  insufficient: "bg-[#F3F4F6] text-[#6B7280]",
};

export function badgeLabel(badge: ReliabilityBadge): "High" | "Medium" | "Low" | "Not enough samples" {
  return LABELS[badge] as ReturnType<typeof badgeLabel>;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The details behind a badge, e.g. "found right 24% · 21 cans · 9 frames · often read as Slide Cheese 145g".
 * Without enough samples it gives only the counts: a percent over a handful of cans would say too much. */
export function reliabilityText(r: ApiReliability): string {
  const counts = [plural(r.true_units, "can", "cans"), plural(r.frames, "frame", "frames")];
  if (r.badge === "insufficient") return `Not enough samples (n = ${counts.join(", ")})`;
  const parts = r.found_right === null ? [] : [`found right ${Math.round(r.found_right * 100)}%`];
  parts.push(...counts);
  if (r.confused_as) parts.push(`often read as ${r.confused_as}`);
  return parts.join(" · ");
}
