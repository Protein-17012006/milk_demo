// Labels and row types for the Products (category) page.
// Every product row comes from the live API (GET /products); this file holds no shelf data.

import type { ApiReliability } from "./api";

export type PrimaryCategory = "Milk" | "Snacks" | "Noodles";
export type CategoryFilterOption = "All" | PrimaryCategory;
/** "Not flagged": the model was sure enough (not under the flag threshold, a SKU matched). It does not mean a
 * person checked the reading; the card's Audit Status says that (auditStatusText). */
export type ProductStatus = "Not flagged" | "Needs Review" | "Low Confidence";
export type StatusFilterOption = "All" | ProductStatus;
export type SortOption =
  | "On-shelf stock (high → low)"
  | "On-shelf stock (low → high)"
  | "Confidence (high → low)"
  | "Name (A → Z)";

export const STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
  "All",
  "Not flagged",
  "Needs Review",
  "Low Confidence",
];

export const SORT_OPTIONS: SortOption[] = [
  "On-shelf stock (high → low)",
  "On-shelf stock (low → high)",
  "Confidence (high → low)",
  "Name (A → Z)",
];

/** The Sort choices of an account: confidence is a number for the team (canReview), not for a viewer. */
export function sortOptions(canReview: boolean): SortOption[] {
  return canReview ? SORT_OPTIONS : SORT_OPTIONS.filter((option) => option !== "Confidence (high → low)");
}

/** Shown where the SKU master has no barcode for a product yet. */
export const NO_BARCODE = "No barcode yet";

/** The Category columns that depend on who looks and on how many stores there are. */
export interface CategoryColumns {
  skuCode: boolean;
  confidence: boolean;
  stores: boolean;
}

/** canReview: the account is in field_team or team_admin. A viewer keeps the one Reliability label under the name. */
export function categoryColumns(canReview: boolean, storeCount: number): CategoryColumns {
  return { skuCode: canReview, confidence: canReview, stores: storeCount > 1 };
}

/** A Store filter with a single store filters nothing. */
export function showStoreFilter(storeCount: number): boolean {
  return storeCount > 1;
}

export const MISMATCH_TYPE_OPTIONS = [
  "None",
  "Wrong Variant (Sugar / Low Sugar)",
  "Low Confidence",
  "Unrecognized SKU",
  "Partial Occlusion",
  "Count Mismatch",
  "Not on the shelf (false reading)",
];

/** is_flagged = TRUE below this confidence (Data Dictionary); the API also returns it as flag_threshold. */
export const MILK_FLAG_THRESHOLD = 0.7;

/** Store dropdown label for "every store"; the count is appended only once the live store list is known. */
export const ALL_STORES_LABEL = "All stores";

/** One row of the Datagent 16-column CV Output, plus the frame facts the validation card shows. */
export interface CvOutputRow {
  reading_id: string;
  capture_id: string;
  store_id: string;
  camera_id: string;
  capture_timestamp: string;
  capture_source: string;
  image_filename: string;
  sku_id: string | null;
  sku_name: string | null;
  unit_count: number;
  confidence_score: number;
  detection_method: "Visual";
  bounding_box: [number, number, number, number][];
  is_flagged: boolean;
  flag_reason: string;
  processing_time_ms: number;
  image_key: string;
  frame_w: number;
  frame_h: number;
  faces_blurred: number;
  pipeline: string;
  /** Signed S3 link (15 min) to the face-blurred frame of this reading; never logged or stored. */
  frame_url: string | null;
}

export interface SkuAudit {
  accuracy: string | null;
  expectedLabel: string;
  mismatchType: string;
  reviewedAt: string | null;
}

export interface SkuProduct {
  id: string;
  name: string;
  modelAlias: string;
  thumbnail: string;
  categories: string[];
  hasMoreCategories?: boolean;
  primaryCategory: PrimaryCategory;
  /** SKU Master brand and subcategory; together they are the product line the page groups by. */
  brand: string | null;
  subcategory: string | null;
  packType: string;
  packSize: string;
  skuCode: string;
  barcode: string;
  brandManufacturer: string;
  categoryPath: string;
  onShelfStock: number;
  confidence: number;
  storesAvailable: number;
  storesTotal: number;
  storeRegion: string;
  status: ProductStatus;
  /** When GET /products/{sku} last filled the card (ms since epoch); null until then. */
  detailFetchedAt: number | null;
  cvOutput: CvOutputRow;
  audit: SkuAudit;
  /** Reliability badge from the last 14 days of labelled frames; absent from older backends. */
  reliability?: ApiReliability;
  /** On the shelf plan of a store (saved, or suggested when none is saved); false from older backends. */
  inShelfPlan: boolean;
  /** The product's place is not in the camera's view: onShelfStock is its last reading, so no total counts it. */
  notInView?: boolean;
  /** Set when the card was opened from the review queue: it shows that flagged reading, not the latest one, and
   * saving a correction checks the queue item off. */
  reviewQueueKey?: string;
}

/** The confidence a row may show: a row without units has only the score of an older reading, so none. */
export function shownConfidence(units: number, confidence: number): number | null {
  return units > 0 ? confidence : null;
}

/** For a card whose SKU is at 0: its frame and boxes are from the last capture that saw it, not from now.
 * timestamp is the reading's capture_timestamp (ISO, UTC+7). */
export function lastSeenNote(units: number, boxes: number, timestamp: string | null): string | null {
  if (units > 0 || boxes === 0 || !timestamp) return null;
  const when = `${timestamp.slice(11, 16)} on ${timestamp.slice(8, 10)}/${timestamp.slice(5, 7)}`;
  return `Not on the shelf at the last check. The frame and its ${boxes} ${boxes === 1 ? "box" : "boxes"} are from ${when}, when it was last seen.`;
}

/** The card's Audit Status: "Validated" only once a person reviewed the reading; an unflagged reading nobody
 * looked at is "Not reviewed". */
export function auditStatusText(status: ProductStatus, reviewedAt: string | null): string {
  if (status !== "Not flagged") return status;
  return reviewedAt ? "Validated" : "Not reviewed";
}

/** What the product list says while it has no rows. approved: the account may read products; loaded: the first read
 * came back; failed: that read did not come back. An approved account is never told to wait for approval. */
export function emptyProductsText(a: { approved: boolean; loaded: boolean; failed: boolean }): string {
  if (!a.approved) return "Products appear once your account is approved.";
  if (a.failed) return "Products could not be loaded. Reload the page to try again.";
  if (!a.loaded) return "Loading products…";
  return "No products match the search and the filters.";
}
