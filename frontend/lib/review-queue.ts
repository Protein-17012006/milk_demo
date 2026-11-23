/**
 * The Products review queue: readings the model was unsure about, waiting for a person to confirm or correct them.
 * Statuses are the Validation Card's (docs/NHAT-P01.md 6.2): "Chờ duyệt" until someone confirms the AI
 * ("Đã xác nhận") or saves a correction ("Đã sửa"). A new flagged reading sets its item back to "Chờ duyệt".
 */

const CHECKED = new Set(["Đã xác nhận", "Đã sửa"]);

/** True until a person has confirmed or corrected the reading; an unknown status is still waiting. */
export const isWaiting = (status: string | null | undefined) => !CHECKED.has(status ?? "");

export interface ReviewSummary {
  waiting: number;
  waitingLowConfidence: number;
  waitingUnrecognized: number;
  checked: number;
}

export function reviewSummary(items: { status?: string | null; flag_reason?: string | null }[]): ReviewSummary {
  const summary: ReviewSummary = { waiting: 0, waitingLowConfidence: 0, waitingUnrecognized: 0, checked: 0 };
  for (const item of items) {
    if (!isWaiting(item.status)) {
      summary.checked += 1;
      continue;
    }
    summary.waiting += 1;
    if (item.flag_reason === "Low Confidence") summary.waitingLowConfidence += 1;
    if (item.flag_reason === "Unrecognized") summary.waitingUnrecognized += 1;
  }
  return summary;
}

/** Waiting items first, newest first within each group. */
export function orderForReview<T extends { status?: string | null; capture_timestamp?: string | null }>(items: T[]): T[] {
  return [...items].sort(
    (a, b) =>
      Number(isWaiting(b.status)) - Number(isWaiting(a.status)) ||
      String(b.capture_timestamp ?? "").localeCompare(String(a.capture_timestamp ?? ""))
  );
}
