/**
 * The Products review queue: readings the model was unsure about, waiting for a person to confirm or correct them.
 * Statuses are the Validation Card's (docs/NHAT-P01.md 6.2): "Chờ duyệt" until someone confirms the AI
 * ("Đã xác nhận") or saves a correction ("Đã sửa"). A new flagged reading sets its item back to "Chờ duyệt".
 */
// Imports are type-only so Node can run the unit tests without the Next.js path aliases.
import type { ApiReviewQueueItem } from "./api";
import type { SkuProduct } from "./products-ui";

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

/** The same picture as PLACEHOLDER_THUMBNAIL in product-thumbnail.ts (a runtime import would break the unit tests). */
const NO_PHOTO = "/images/products/placeholder.svg";

/** The waiting queue item of this very reading, if there is one: a correction saved for the reading checks it off. */
export function queueKeyForReading(
  items: Pick<ApiReviewQueueItem, "queue_key" | "reading_id" | "status">[],
  readingId: string | null | undefined
): string | undefined {
  if (!readingId) return undefined;
  return items.find((item) => item.reading_id === readingId && isWaiting(item.status))?.queue_key;
}

/**
 * The Validation Card for a queue item: the product's own name and photo (row: its Products row, if it has one) with
 * the flagged reading's numbers, boxes and frame, so the reviewer corrects what was flagged and not the product's
 * latest reading. now: ms since epoch, the age of the signed frame link.
 */
export function cardFromQueueItem(det: ApiReviewQueueItem, row: SkuProduct | undefined, now: number): SkuProduct {
  const name = det.sku_name || (det.flag_reason === "Unrecognized" ? "Unrecognized" : det.sku_id);
  const base: SkuProduct = row ?? {
    id: det.sku_id,
    name,
    modelAlias: det.model_alias || det.sku_id,
    thumbnail: NO_PHOTO,
    categories: [],
    primaryCategory: "Milk",
    brand: null,
    subcategory: null,
    packType: "—",
    packSize: "—",
    skuCode: det.model_alias || det.sku_id,
    barcode: "—",
    brandManufacturer: "—",
    categoryPath: "—",
    onShelfStock: 0,
    confidence: 0,
    storesAvailable: 0,
    storesTotal: 0,
    storeRegion: det.store_id,
    status: "Needs Review",
    detailFetchedAt: null,
    cvOutput: {
      reading_id: det.reading_id,
      capture_id: det.capture_id,
      store_id: det.store_id,
      camera_id: det.camera_id,
      capture_timestamp: det.capture_timestamp,
      capture_source: "CCTV",
      image_filename: "—",
      sku_id: det.sku_id,
      sku_name: name,
      unit_count: 0,
      confidence_score: 0,
      detection_method: "Visual",
      bounding_box: [],
      is_flagged: true,
      flag_reason: det.flag_reason,
      processing_time_ms: 0,
      image_key: "—",
      frame_w: 2560,
      frame_h: 1440,
      faces_blurred: 0,
      pipeline: "",
      frame_url: null,
    },
    audit: { accuracy: null, expectedLabel: "", mismatchType: "None", reviewedAt: null },
    inShelfPlan: false,
  };
  return {
    ...base,
    // where the product's place is now says nothing of this reading: the card shows its count and time
    notInView: false,
    notInViewInfo: undefined,
    status: det.flag_reason === "Low Confidence" ? "Low Confidence" : "Needs Review",
    detailFetchedAt: now,
    reviewQueueKey: det.queue_key,
    cvOutput: {
      ...base.cvOutput,
      reading_id: det.reading_id,
      capture_id: det.capture_id,
      store_id: det.store_id,
      camera_id: det.camera_id,
      capture_timestamp: det.capture_timestamp,
      image_filename: "—",
      image_key: "—",
      unit_count: Number(det.unit_count),
      confidence_score: Number(det.confidence_score),
      bounding_box: det.bounding_box ?? [],
      is_flagged: true,
      flag_reason: det.flag_reason,
      processing_time_ms: 0,
      faces_blurred: 0,
      frame_url: det.frame_presigned_url,
    },
    // a correction of another reading of this product says nothing about this one
    audit: { accuracy: null, expectedLabel: row ? row.id : "", mismatchType: "None", reviewedAt: null },
  };
}

/**
 * Whether the card's form holds a correction: the label was set to another product, or a mismatch type was picked.
 * The backend refuses a correction that changes nothing (NOTHING_CHANGED) by the same rule on what the card sends:
 * sku_id = modelLabel, corrected_sku_id = expectedLabel, discrepancy_category = mismatchType.
 */
export function correctionChanged(modelLabel: string, expectedLabel: string, mismatchType: string): boolean {
  return (expectedLabel !== "" && expectedLabel !== modelLabel) || mismatchType !== "None";
}

/** What the page says after a saved correction: whether a queue item was checked off, and where the frame goes.
 * The frame is asked for, not promised: the hourly rule serves one request an hour, and drops one whose
 * frame can no longer be read. */
export function correctionToast(checkedOff: boolean, labelRequest: string | null | undefined): string {
  return (
    "Saved the correction." +
    (checkedOff ? " The reading is checked off in the review queue." : "") +
    (labelRequest === "pending" ? " Its frame is in line for the labelling queue." : "")
  );
}

/**
 * The card's Save Correction button: locked until the form holds a change, while the save is on its way, and for
 * the moment "Saved" shows before the card closes (a second click then must not save the correction twice).
 */
export function correctionButton(changed: boolean, saving: boolean, saved: boolean): { disabled: boolean; text: string } {
  if (saved) return { disabled: true, text: "Saved ✓" };
  if (saving && changed) return { disabled: true, text: "Saving…" };
  return { disabled: !changed || saving, text: "Save Correction" };
}
