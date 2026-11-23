"use client";

import { AWS_CONFIG } from "./config";

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
  top_50_sku_accuracy: number | null;
  top_50_scope_note: string;
  captures_count: number;
  flag_threshold: number;
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

    getKpi: () =>
      requestWithAuth("/kpi", getIdToken) as Promise<ApiKpiResponse>,

    getReportsSeries: () =>
      requestWithAuth("/reports/series", getIdToken) as Promise<ApiReportsSeriesResponse>,

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
  };
}

/** Map live SKU packaging name / brand to local crisp product thumbnail. */
export function resolveProductThumbnail(
  skuName: string,
  brand?: string | null
): string {
  const text = `${skuName} ${brand ?? ""}`.toLowerCase();
  if (text.includes("th true")) return "/images/products/thtruemilk.png";
  if (text.includes("milo")) return "/images/products/milo.png";
  if (text.includes("dalat")) return "/images/products/dalatmilk.png";
  if (text.includes("probi") || text.includes("yakult"))
    return "/images/products/probi.png";
  if (text.includes("óc chó") || text.includes("oc cho") || text.includes("hạt"))
    return "/images/products/occho.png";
  if (text.includes("vinamilk") || text.includes("dutch") || text.includes("fami"))
    return "/images/products/vinamilk.png";
  if (text.includes("hảo hảo") || text.includes("hao hao"))
    return "/images/products/haohao.png";
  if (text.includes("omachi")) return "/images/products/omachi.png";
  if (text.includes("3 miền") || text.includes("3 mien"))
    return "/images/products/3mien.png";
  if (text.includes("cung đình") || text.includes("cung dinh"))
    return "/images/products/cungdinh.png";
  // No photo for this SKU yet (e.g. the Slide snacks): a neutral box, never another product's photo.
  return "/images/products/placeholder.svg";
}
