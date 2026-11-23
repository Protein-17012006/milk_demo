// Labels and row types for the Products (category) page.
// Every product row comes from the live API (GET /products); this file holds no shelf data.

export type PrimaryCategory = "Milk" | "Snack" | "Noodles";
export type CategoryFilterOption = "All" | PrimaryCategory;
export type ProductStatus = "Validated" | "Needs Review" | "Low Confidence";
export type StatusFilterOption = "All" | ProductStatus;
export type SortOption =
  | "On-shelf stock (high → low)"
  | "On-shelf stock (low → high)"
  | "Confidence (high → low)"
  | "Name (A → Z)";

export const STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
  "All",
  "Validated",
  "Needs Review",
  "Low Confidence",
];

export const SORT_OPTIONS: SortOption[] = [
  "On-shelf stock (high → low)",
  "On-shelf stock (low → high)",
  "Confidence (high → low)",
  "Name (A → Z)",
];

export const MISMATCH_TYPE_OPTIONS = [
  "None",
  "Wrong Variant (Sugar / Low Sugar)",
  "Low Confidence",
  "Unrecognized SKU",
  "Partial Occlusion",
  "Count Mismatch",
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
}
