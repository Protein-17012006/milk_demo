"use client";

import { AWS_CONFIG } from "./config";
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
}

export interface ApiProductsResponse {
  items: ApiProduct[];
  total: number;
  unrecognized_units: number;
  stores_total: number;
  flag_threshold: number;
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
    blocked_reason: BlockedReason | null;
  };
  oos_now?: { count: number | null; as_of: string | null; blocked_reason: BlockedReason | null };
  top_50_sku_accuracy?: {
    value: number | null;
    n_frames: number;
    scope_note: string;
    blocked_reason: BlockedReason | null;
  };
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
  duration_min: number | null;
}

export interface ApiShelfEventsResponse {
  items: ApiShelfEvent[];
  next_cursor: string | null;
}

/** t is YYYY-MM-DD, or YYYYMMDD-HH when the period is today. */
export interface ApiTrendPoint {
  t: string;
  value: number | null;
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

/** One day of GET /reports/series: units found per capture, from the backend captures table. */
export interface ApiReportsSeriesPoint {
  date: string; // YYYY-MM-DD (UTC+7)
  avg_units: number;
  max_units: number;
  captures: number;
}

export interface ApiReportsSeriesResponse {
  series: ApiReportsSeriesPoint[];
}

// --- Model page (GET/PUT /model/*) -------------------------------------------------------------------

export type AuditStatus = "pending" | "done" | "skipped";

/** One box the model drew on a sampled frame; sku_id is the model label (null = UNRECOGNIZED). */
export interface ApiAuditBox {
  box_id: number;
  sku_id: string | null;
  conf: number;
  box: [number, number, number, number]; // x, y, w, h in frame pixels
}

export interface ApiAuditListItem {
  audit_id: string;
  camera_id: string;
  capture_id: string;
  capture_timestamp: string;
  model_version: string;
  status: AuditStatus;
  n_boxes: number;
  labeled_by?: string | null;
}

export interface ApiAuditListResponse {
  items: ApiAuditListItem[];
  counts: Record<AuditStatus, number>;
}

export interface ApiAuditVerdict {
  box_id: number;
  verdict: "correct" | "wrong_sku" | "not_product";
  true_sku_id?: string;
}

export interface ApiAuditDetail {
  audit_id: string;
  store_id: string;
  camera_id: string;
  capture_id: string;
  capture_timestamp: string;
  model_version: string;
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
}

export interface ApiKpiValue {
  value: number | null;
  target: [string, number];
  met: boolean | null;
  n: number;
  exact_or_minor?: number | null;
}

export interface ApiModelSummary {
  n_audits: number;
  kpis: Record<string, ApiKpiValue>;
  per_sku: {
    sku_id: string;
    model_units: number;
    true_units: number;
    id_accuracy: number | null;
    missed_units: number;
    confused_as: string | null;
    confused_count: number;
  }[];
  confusion: { rows: string[]; cols: string[]; cells: Record<string, number> };
  by_day: {
    day: string;
    audits: number;
    overall_identification_accuracy: number | null;
    unit_count_mae: number | null;
    exact_or_minor_rate: number | null;
  }[];
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

  let res = await execute(false);
  if (res.status === 401) {
    res = await execute(true);
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

    listAudits: (status?: AuditStatus, days = 7) => {
      const sp = new URLSearchParams({ days: String(days) });
      if (status) sp.set("status", status);
      return requestWithAuth(`/model/audits?${sp.toString()}`, getIdToken) as Promise<ApiAuditListResponse>;
    },

    getAudit: (auditId: string) =>
      requestWithAuth(`/model/audits/${encodeURIComponent(auditId)}`, getIdToken) as Promise<ApiAuditDetail>,

    saveAudit: (
      auditId: string,
      body: { verdicts: ApiAuditVerdict[]; missed: { sku_id: string; x: number; y: number }[] }
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
