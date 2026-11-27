"use client";

import { AWS_CONFIG } from "./config";
import { retryRead } from "./retry";
import { dashboardQuery, type DashboardQuery } from "./shelf-ui";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type ReliabilityBadge = "high" | "medium" | "low" | "insufficient";

/** How far one SKU can be trusted, from the labelled scoring frames of the last 14 days. */
export interface ApiReliability {
  badge: ReliabilityBadge;
  named_right: number | null; // boxes named this SKU and right / boxes named this SKU
  found_right: number | null; // boxes named this SKU and right / true cans of it
  true_units: number; // true cans of it in the frames that had one
  frames: number; // frames with a true can
  confused_as: string | null; // product name the model most often gave its true cans
}

export interface ApiProduct {
  sku_id: string;
  sku_name: string;
  sku_name_en: string | null;
  model_alias: string;
  brand: string | null;
  manufacturer: string | null;
  category: string | null;
  subcategory: string | null;
  pack_type: string | null;
  pack_size: string | null;
  barcode: string | null;
  image_url: string | null;
  in_sku_master: boolean;
  unit_count: number;
  confidence_score: number;
  is_flagged: boolean;
  flag_reason: string;
  stores_available: number;
  stores_total: number;
  capture_id: string | null;
  capture_timestamp: string | null;
  processing_time_ms: number;
  reliability?: ApiReliability; // older backends leave it out
}

export interface ApiProductsResponse {
  items: ApiProduct[];
  total: number;
  unrecognized_units: number;
  stores_total: number;
  flag_threshold: number;
  displays?: ApiDisplayStatus[]; // one per camera; older backends leave it out
}

/** Whether a camera sees the display cabinet. `since` is when the current state began (ISO, UTC+7). */
export interface ApiDisplayStatus {
  camera_id: string;
  store_id: string;
  visible: boolean;
  since: string | null;
  last_visible_at: string | null;
}

export interface ApiProductDetail {
  sku_id: string;
  in_sku_master: boolean;
  product_information: {
    sku_id: string;
    sku_name_vi?: string | null;
    brand?: string | null;
    manufacturer?: string | null;
    category?: string | null;
    pack_type?: string | null;
    pack_size?: string | null;
    barcode?: string | null;
  };
  cv_output: {
    reading_id: string | null;
    capture_id: string | null;
    store_id: string | null;
    camera_id: string | null;
    capture_timestamp: string | null;
    capture_source: string;
    image_filename: string | null;
    image_key: string | null;
    frame_presigned_url: string | null;
    unit_count: number;
    smoothed_count: number;
    confidence_score: number;
    detection_method: "Visual";
    bounding_box: [number, number, number, number][];
    is_flagged: boolean;
    flag_reason: string;
    processing_time_ms: number;
    faces_blurred: number;
  };
  validation: {
    result: "Đạt" | "Không đạt" | "Pending";
    status: "Chờ duyệt" | "Đã sửa" | "Đã xác nhận" | string;
    expected_label: string;
    mismatch_type: string;
    reviewed_at: string | null;
    accuracy: number | null;
  };
}

export interface ApiStore {
  store_id: string;
  store_name: string;
  district?: string;
  address?: string;
  camera_id?: string;
  status?: string;
  categories_in_view?: string[];
  last_capture_timestamp: string | null;
  has_recent_capture: boolean;
}

export interface ApiStoresResponse {
  items: ApiStore[];
  total: number;
  active_monitored: number;
}

export interface ApiReviewQueueItem {
  store_id: string;
  queue_key: string;
  reading_id: string;
  capture_id: string;
  camera_id: string;
  capture_timestamp: string;
  sku_id: string;
  sku_name: string | null;
  model_alias?: string;
  unit_count: number;
  confidence_score: number;
  flag_reason: string;
  bounding_box: [number, number, number, number][];
  frame_presigned_url: string | null;
  status: string;
  updated_at?: string;
  reviewed_by?: string;
  reviewed_at?: string;
}

export interface ApiReviewQueueResponse {
  items: ApiReviewQueueItem[];
  total: number;
}

export interface ApiKpiResponse {
  active_stores_monitored: number;
  total_stores: number;
  total_on_shelf_units: number;
  unrecognized_units: number;
  avg_processing_time_ms: number;
  top_50_scope_note: string;
  captures_count: number;
  flag_threshold: number;
  // Shelf numbers for the Dashboard filters (spec 2026-11-24): null with blocked_reason when the data cannot say
  days?: number;
  osa?: { value: number | null; previous: number | null; blocked_reason: BlockedReason | null };
  restock_rate?: {
    units_per_day: number | null;
    previous_units_per_day: number | null;
    change_pct: number | null;
    measured_days?: number; // days of the period that have a counted check; older backends leave it out
    blocked_reason: BlockedReason | null;
  };
  // one per camera of the chosen stores: whether it sees the display now (older backends leave it out)
  displays?: ApiDisplayStatus[];
  oos_now?: { count: number | null; as_of: string | null; blocked_reason: BlockedReason | null };
  // Hours of the period: measured, open, and open hours in which the camera could not see the display.
  // null when the store has no opening hours (an older backend leaves the field out).
  coverage?: ApiCoverage | null;
  // How often confirmed alerts were right; value is null (blocked_reason "few_verified") below 10 confirmed events.
  alert_accuracy?: ApiAlertAccuracy;
  top_50_sku_accuracy?: {
    value: number | null;
    n_frames: number;
    scope_note: string;
    blocked_reason: BlockedReason | null;
  };
}

export type ShelfVerdict = "right" | "wrong" | "unsure";

export interface ApiAlertAccuracy {
  value: number | null;
  n: number; // right + wrong
  unsure: number;
  by_type?: Record<string, Record<ShelfVerdict, number>>;
  blocked_reason: "few_verified" | null;
}

/** Links (valid 15 minutes) to the two photos of a shelf event; null for a photo that was not kept. */
export interface ApiEventPhotos {
  before_url: string | null;
  after_url: string | null;
}

export interface ApiCoverage {
  measured_hours: number;
  open_hours: number;
  display_away_hours: number;
}

export type BlockedReason = "no_hours" | "no_expected" | "no_checks" | "no_previous" | "no_labels";
export type ShelfEventType = "OOS" | "LOW_STOCK" | "DEPLETED" | "RESTOCKED";
export type TrendMetric = "total_stock" | "oos" | "accuracy" | "restock_volume" | "osa";

/** One shelf event; `at` is the 5-minute bucket YYYYMMDD-HHMM (UTC+7) where the change began. */
export interface ApiShelfEvent {
  event_key: string;
  store_id: string;
  store_name: string;
  sku_id: string;
  sku_name: string;
  type: ShelfEventType;
  at: string;
  delta: number;
  level_before: number;
  level_after: number;
  duration_min?: number | null; // left out when empty: only a RESTOCKED that ended an out-of-stock has it
  // Set when the shelf was not seen for a while before this change: buckets of the last measured check before the
  // gap and of the first one after it.
  after_gap?: boolean;
  gap_from?: string;
  gap_to?: string;
  verdict?: ShelfVerdict; // what the team confirmed, once someone has
  badge?: ReliabilityBadge; // reliability of the SKU; older backends leave it out
  uncertain?: true; // set when the badge is "low"
}

export interface ApiShelfEventsResponse {
  items: ApiShelfEvent[];
  next_cursor: string | null;
}

/** t is YYYY-MM-DD, or YYYYMMDD-HH when the period is today. */
export interface ApiTrendPoint {
  t: string;
  value: number | null;
  unmeasured_hours?: number | null; // hours of this point in which the display was out of view
}

export interface ApiTrendsResponse {
  metric: TrendMetric;
  days: number;
  points: ApiTrendPoint[];
}

export interface ApiShelfPlan {
  store_id: string;
  open_time: string | null;
  close_time: string | null;
  expected_skus: string[];
  source: "saved" | "suggested";
  suggested: { sku_id: string; last_seen: string }[];
  updated_by: string | null;
  updated_at: string | null;
}

/** One day of GET /reports/series: units of the expected SKUs per counted check, from the day rollups. */
export interface ApiReportsSeriesPoint {
  date: string; // YYYY-MM-DD (UTC+7)
  avg_units: number;
  max_units: number;
  checks: number;
  unmeasured_hours?: number;
}

export interface ApiReportsSeriesResponse {
  series: ApiReportsSeriesPoint[];
}

// --- Model page (GET/PUT /model/*) -------------------------------------------------------------------

export type AuditStatus = "pending" | "done" | "skipped";

/** One box the model drew on a sampled frame; sku_id is the model label (null = UNRECOGNIZED). On a review frame a box
 * may need a flavour (the auto-labeller could not name it: sku_id null, no Right) and names its can (track_id). */
export interface ApiAuditBox {
  box_id: number;
  sku_id: string | null;
  conf: number;
  box: [number, number, number, number]; // x, y, w, h in frame pixels
  needs_flavour?: boolean;
  track_id?: string;
}

// scoring frames count in the accuracy numbers; training frames only teach the flavour gallery; review frames carry
// the cans the auto-labeller could not decide, and are never scored either
export type AuditPurpose = "scoring" | "training" | "review";

export interface ApiAuditListItem {
  audit_id: string;
  camera_id: string;
  capture_id: string;
  capture_timestamp: string;
  model_version: string;
  purpose: AuditPurpose;
  status: AuditStatus;
  n_boxes: number;
  labeled_by?: string | null;
  label_rule?: string | null; // the rule it was labelled under ("B" now, "A" before 25/11); null before rules, or not labelled yet
}

export interface ApiAuditListResponse {
  items: ApiAuditListItem[];
  counts: Record<AuditStatus, number>;
}

export interface ApiAuditVerdict {
  box_id: number;
  verdict: "correct" | "wrong_sku" | "not_product" | "out_of_scope";
  true_sku_id?: string;
}

export interface ApiAuditDetail {
  audit_id: string;
  store_id: string;
  camera_id: string;
  capture_id: string;
  capture_timestamp: string;
  model_version: string;
  purpose: AuditPurpose;
  status: AuditStatus;
  ai_boxes: ApiAuditBox[];
  verdicts: ApiAuditVerdict[];
  missed: { sku_id: string; x: number; y: number }[];
  frame_url: string | null; // signed for 15 minutes; never logged
  sku_choices: { label: string; name: string }[];
  labeled_by?: string;
  labeled_at?: string;
  skip_reason?: string;
  skip_note?: string;
  label_rule?: string;
  misses_checked?: boolean;
}

/** A 95% interval from resampling whole labelled frames; null under 2 frames. */
export type ApiInterval = [number, number] | null;

/** One ratio or mean over labelled frames: value null when nothing was counted (never 0); n = sum of denominators. */
export interface ApiStat {
  value: number | null;
  ci: ApiInterval;
  n: number;
}

export interface ApiKpiValue {
  value: number | null;
  target: [string, number];
  met: boolean | null;
  n: number;
  exact_or_minor?: number | null;
  ci?: ApiInterval; // every KPI but processing time
}

export interface ApiPerSkuRow {
  sku_id: string;
  model_units: number;
  true_units: number;
  id_accuracy: number | null; // named right: boxes named this SKU and right / boxes named this SKU
  missed_units: number;
  confused_as: string | null;
  confused_count: number;
  // older backends leave the rest out
  id_accuracy_ci?: ApiInterval;
  found_right?: number | null; // boxes named this SKU and right / true cans of it
  found_right_ci?: ApiInterval;
  bias_per_frame?: number | null; // mean of model - truth over the frames where either side counted it
  bias_per_frame_ci?: ApiInterval;
  frames?: number; // frames with a true can
  days?: number; // days of those frames (UTC+7)
  enough?: boolean; // 10 frames, 20 true cans, 2 days
  badge?: ReliabilityBadge;
}

export type DayPeriod = "morning" | "afternoon" | "evening";

export interface ApiPeriodSku {
  named_right: number | null;
  found_right: number | null;
  model_units: number;
  true_units: number;
  frames: number;
  days: number;
  enough: boolean;
}

export interface ApiPeriod {
  frames: number;
  overall_identification_accuracy: ApiStat;
  presence_agree: ApiStat;
  per_sku: Record<string, ApiPeriodSku>;
}

/** The Dashboard's 5-minute checks against the truth of the labelled frame inside each; n = SKU rows. */
export interface ApiCheckLevel {
  frames: number;
  count_mae: ApiStat;
  count_bias: ApiStat; // check minus truth: positive counts too many
  presence_agree: ApiStat;
}

/** The worker's display check against the labellers on scoring frames. */
export interface ApiDisplayCheck {
  agree: ApiStat;
  false_not_visible: number;
  false_visible: number;
}

export interface ApiModelSummary {
  n_audits: number;
  old_rule_frames: number; // done frames not labelled under the current rule (B)
  out_of_scope_share: { value: number | null; n: number }; // out_of_scope boxes / all AI boxes; n = boxes
  kpis: Record<string, ApiKpiValue>;
  per_sku: ApiPerSkuRow[];
  confusion: { rows: string[]; cols: string[]; cells: Record<string, number> };
  by_day: {
    day: string;
    audits: number;
    overall_identification_accuracy: number | null;
    unit_count_mae: number | null;
    exact_or_minor_rate: number | null;
  }[];
  // older backends leave these four out; n of presence = SKU rows (one SKU in one frame)
  presence?: { agree: ApiStat; false_empty: ApiStat; missed_empty: ApiStat };
  by_period?: Record<DayPeriod, ApiPeriod>;
  check_level?: ApiCheckLevel;
  display_check?: ApiDisplayCheck;
  model_versions: string[];
  range: { days: number; model_version: string };
}

/** Health of one camera-hour; shares are absent when there was nothing to divide by. */
export interface ApiModelHealthItem {
  camera_id: string;
  hour: string; // YYYYMMDD-HH, UTC+7
  captures: number;
  model_versions?: string[];
  conf_median?: number;
  conf_mean?: number;
  flagged_row_pct?: number;
  unrecognized_box_pct?: number;
  units_median?: number;
  units_min?: number;
  units_max?: number;
  jitter?: number;
  duplicate_pairs?: number;
  processing_ms_median?: number;
  processing_ms_p90?: number;
  latency_ms_median?: number;
}

export interface ApiSettingsResponse {
  account: {
    email: string;
    groups: string[];
    readonly: boolean;
  };
  preferences: {
    date_format: string;
    default_landing: string;
  };
  timezone: {
    value: string;
    readonly: boolean;
  };
  flag_threshold: {
    value: number;
    readonly: boolean;
  };
  stores: ApiStore[];
}

export type TokenGetter = (forceRefresh?: boolean) => Promise<string | null>;

async function requestWithAuth(
  path: string,
  getIdToken: TokenGetter,
  init: RequestInit = {},
  expectText = false
): Promise<unknown> {
  const execute = async (forceRefresh: boolean) => {
    const token = await getIdToken(forceRefresh);
    const headers = new Headers(init.headers);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return fetch(`${AWS_CONFIG.apiBaseUrl}${path}`, {
      ...init,
      headers,
    });
  };

  // reads are tried again when Lambda is busy (lib/retry.ts); writes are sent once
  const isRead = !init.method || init.method.toUpperCase() === "GET";
  const send = (forceRefresh: boolean) => (isRead ? retryRead(() => execute(forceRefresh)) : execute(forceRefresh));

  let res = await send(false);
  if (res.status === 401) {
    res = await send(true);
  }

  if (!res.ok) {
    let code = `HTTP_${res.status}`;
    let message = `Request failed (${res.status})`;
    try {
      const errBody = (await res.json()) as {
        error?: string;
        message?: string;
      };
      if (errBody.error) code = errBody.error;
      if (errBody.message) message = errBody.message;
    } catch {
      // ignore non-json error body
    }
    throw new ApiError(res.status, code, message);
  }

  return expectText ? res.text() : res.json();
}

export function createApiClient(getIdToken: TokenGetter) {
  return {
    getHealth: async () => {
      const res = await fetch(`${AWS_CONFIG.apiBaseUrl}/health`);
      return res.json() as Promise<{
        status: string;
        service: string;
        region: string;
        flag_threshold: number;
      }>;
    },

    getProducts: (params?: {
      q?: string;
      category?: string;
      status?: string;
      sort?: string;
    }) => {
      const sp = new URLSearchParams();
      if (params?.q) sp.set("q", params.q);
      if (params?.category) sp.set("category", params.category);
      if (params?.status) sp.set("status", params.status);
      if (params?.sort) sp.set("sort", params.sort);
      const qs = sp.toString();
      return requestWithAuth(
        `/products${qs ? `?${qs}` : ""}`,
        getIdToken
      ) as Promise<ApiProductsResponse>;
    },

    getProductDetail: (skuId: string) =>
      requestWithAuth(
        `/products/${encodeURIComponent(skuId)}`,
        getIdToken
      ) as Promise<ApiProductDetail>,

    getStores: () =>
      requestWithAuth("/stores", getIdToken) as Promise<ApiStoresResponse>,

    searchCatalog: (q: string) =>
      requestWithAuth(
        `/search?q=${encodeURIComponent(q)}`,
        getIdToken
      ) as Promise<{ products: ApiProduct[]; total: number }>,

    getReviewQueue: (status?: string) =>
      requestWithAuth(
        `/review-queue${status ? `?status=${encodeURIComponent(status)}` : ""}`,
        getIdToken
      ) as Promise<ApiReviewQueueResponse>,

    submitCorrection: (payload: {
      store_id: string;
      queue_key?: string;
      reading_id?: string;
      capture_id?: string;
      sku_id: string;
      corrected_sku_id?: string;
      corrected_count?: number;
      correction_type?: string;
      discrepancy_category?: string; // the field the backend stores; correction_type alone was dropped
      action?: "correct" | "confirm";
      notes?: string;
    }) =>
      requestWithAuth("/corrections", getIdToken, {
        method: "POST",
        body: JSON.stringify(payload),
      }),

    importSkuMaster: (items: Record<string, unknown>[]) =>
      requestWithAuth("/imports/sku-master", getIdToken, {
        method: "POST",
        body: JSON.stringify({ items }),
      }),

    importStoreList: (items: Record<string, unknown>[]) =>
      requestWithAuth("/imports/store-list", getIdToken, {
        method: "POST",
        body: JSON.stringify({ items }),
      }),

    getKpi: (p: DashboardQuery = {}) =>
      requestWithAuth(`/kpi${dashboardQuery(p)}`, getIdToken) as Promise<ApiKpiResponse>,

    getReportsSeries: (p: DashboardQuery = {}) =>
      requestWithAuth(`/reports/series${dashboardQuery(p)}`, getIdToken) as Promise<ApiReportsSeriesResponse>,

    getTrends: (metric: TrendMetric, p: DashboardQuery = {}) =>
      requestWithAuth(`/reports/trends${dashboardQuery({ ...p, metric })}`, getIdToken) as Promise<ApiTrendsResponse>,

    getShelfEvents: (p: DashboardQuery = {}) =>
      requestWithAuth(`/shelf-events${dashboardQuery(p)}`, getIdToken) as Promise<ApiShelfEventsResponse>,

    getShelfEventPhotos: (storeId: string, eventKey: string) =>
      requestWithAuth(
        `/shelf-events/photos?store_id=${encodeURIComponent(storeId)}&event_key=${encodeURIComponent(eventKey)}`,
        getIdToken
      ) as Promise<ApiEventPhotos>,

    // The event key goes in the body: it holds spaces and "&".
    saveShelfEventVerdict: (storeId: string, eventKey: string, verdict: ShelfVerdict) =>
      requestWithAuth("/shelf-events/verdict", getIdToken, {
        method: "PUT",
        body: JSON.stringify({ store_id: storeId, event_key: eventKey, verdict }),
      }) as Promise<{ event_key: string; verdict: ShelfVerdict }>,

    getShelfPlan: (storeId: string) =>
      requestWithAuth(`/stores/${encodeURIComponent(storeId)}/shelf-plan`, getIdToken) as Promise<ApiShelfPlan>,

    saveShelfPlan: (storeId: string, body: { open_time: string; close_time: string; expected_skus: string[] }) =>
      requestWithAuth(`/stores/${encodeURIComponent(storeId)}/shelf-plan`, getIdToken, {
        method: "PUT",
        body: JSON.stringify(body),
      }) as Promise<ApiShelfPlan>,

    getSettings: () =>
      requestWithAuth("/settings", getIdToken) as Promise<ApiSettingsResponse>,

    updateSettings: (payload: {
      date_format: string;
      default_landing: string;
    }) =>
      requestWithAuth("/settings", getIdToken, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),

    exportCvOutputCsv: () =>
      requestWithAuth("/exports/cv-output.csv", getIdToken, {}, true) as Promise<string>,

    exportCaptureLogCsv: () =>
      requestWithAuth("/exports/capture-log.csv", getIdToken, {}, true) as Promise<string>,

    // oldRule: only the done scoring frames labelled under an older rule, for "Relabel them"
    listAudits: (status?: AuditStatus, days = 7, options: { oldRule?: boolean } = {}) => {
      const sp = new URLSearchParams({ days: String(days) });
      if (status) sp.set("status", status);
      if (options.oldRule) sp.set("old_rule", "1");
      return requestWithAuth(`/model/audits?${sp.toString()}`, getIdToken) as Promise<ApiAuditListResponse>;
    },

    getAudit: (auditId: string) =>
      requestWithAuth(`/model/audits/${encodeURIComponent(auditId)}`, getIdToken) as Promise<ApiAuditDetail>,

    saveAudit: (
      auditId: string,
      body: {
        verdicts: ApiAuditVerdict[];
        missed: { sku_id: string; x: number; y: number }[];
        misses_checked: boolean;
      }
    ) =>
      requestWithAuth(`/model/audits/${encodeURIComponent(auditId)}`, getIdToken, {
        method: "PUT",
        body: JSON.stringify(body),
      }) as Promise<ApiAuditDetail>,

    skipAudit: (auditId: string, reason: string, note?: string) =>
      requestWithAuth(`/model/audits/${encodeURIComponent(auditId)}/skip`, getIdToken, {
        method: "POST",
        body: JSON.stringify({ reason, note: note ?? "" }),
      }) as Promise<ApiAuditDetail>,

    getModelSummary: (days: number, modelVersion?: string) => {
      const sp = new URLSearchParams({ days: String(days) });
      if (modelVersion && modelVersion !== "all") sp.set("model_version", modelVersion);
      return requestWithAuth(`/model/summary?${sp.toString()}`, getIdToken) as Promise<ApiModelSummary>;
    },

    getModelHealth: (days: number) =>
      requestWithAuth(`/model/health?days=${days}`, getIdToken) as Promise<{ items: ApiModelHealthItem[] }>,
  };
}
