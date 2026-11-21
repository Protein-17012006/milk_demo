"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  ChevronDown,
  Download,
  MoreHorizontal,
  Search,
  Upload,
  X,
} from "lucide-react";
import { useSidebarSearch } from "@/components/layout/SidebarContext";
import { useAuth } from "@/lib/auth";
import {
  createApiClient,
  resolveProductThumbnail,
  type ApiProduct,
  type ApiReviewQueueItem,
  type ApiStore,
} from "@/lib/api";
import {
  CATEGORY_FILTER_OPTIONS,
  CATEGORY_STORE_OPTIONS,
  SKU_PRODUCTS,
  SORT_OPTIONS,
  STATUS_FILTER_OPTIONS,
  UNMATCHED_REVIEW_QUEUE,
  type CategoryFilterOption,
  type SkuProduct,
  type SortOption,
  type StatusFilterOption,
} from "@/data/category-mock";
import { ProductDetailsModal } from "./ProductDetailsModal";

interface ToolbarDropdownProps<T extends string> {
  label: string;
  value: T;
  options: T[];
  onChange: (val: T) => void;
}

function ToolbarDropdown<T extends string>({
  label,
  value,
  options,
  onChange,
}: ToolbarDropdownProps<T>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="flex h-[36px] items-center gap-[6px] rounded-[8px] border border-[#E5E7EB] bg-white pl-[12px] pr-[10px] text-[12px] transition-colors hover:border-[#D1D5DB] cursor-pointer"
      >
        <span className="font-normal text-[#6B7280]">{label}</span>
        <span className="font-semibold text-[#111827] whitespace-nowrap">
          {value}
        </span>
        <ChevronDown
          className={`h-[14px] w-[14px] shrink-0 text-[#6B7280] transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
          strokeWidth={1.8}
        />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute right-0 top-[42px] z-30 min-w-[200px] rounded-[10px] border border-[#E5E7EB] bg-white p-1 shadow-[0_8px_22px_rgba(0,0,0,0.08)]"
        >
          {options.map((opt) => {
            const active = opt === value;
            return (
              <li key={opt}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    onChange(opt);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between gap-3 rounded-[7px] px-2.5 py-2 text-left text-[12.5px] transition-colors cursor-pointer ${
                    active
                      ? "bg-[#FFF5EC] font-semibold text-[#EE730A]"
                      : "text-[#111827] hover:bg-[#F7F8FA]"
                  }`}
                >
                  <span className="whitespace-nowrap">{opt}</span>
                  {active && <Check className="h-3.5 w-3.5 shrink-0" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.7) return "#1A932E";
  if (confidence >= 0.5) return "#FFCC00";
  return "#FF8D28";
}

function mapApiProductToSkuProduct(p: ApiProduct): SkuProduct {
  const catLower = (p.category || "Milk").toLowerCase();
  const primaryCategory: SkuProduct["primaryCategory"] = catLower.includes(
    "noodle"
  )
    ? "Noodles"
    : catLower.includes("snack")
      ? "Snack"
      : "Milk";

  const status: SkuProduct["status"] = p.is_flagged
    ? p.confidence_score < 0.7
      ? "Low Confidence"
      : "Needs Review"
    : "Validated";

  return {
    id: p.sku_id,
    name: p.sku_name,
    modelAlias: p.model_alias || p.sku_id,
    thumbnail: resolveProductThumbnail(p.sku_name, p.brand),
    categories: [p.category || "Milk", p.subcategory || p.brand || "SKU"].filter(
      Boolean
    ),
    primaryCategory,
    packType: p.pack_type || "Carton",
    packSize: p.pack_size || "—",
    skuCode: p.model_alias || p.sku_id,
    barcode: p.barcode || "Pending SKU Master",
    brandManufacturer: p.manufacturer || p.brand || "Unassigned",
    categoryPath: [p.category || "Milk", p.subcategory]
      .filter(Boolean)
      .join(" / "),
    onShelfStock: p.unit_count,
    confidence: p.confidence_score,
    storesAvailable: p.stores_available,
    storesTotal: p.stores_total,
    storeRegion: "DEMO-S01",
    status,
    cvOutput: {
      reading_id: p.capture_id ? `RD-${p.capture_id}` : "—",
      capture_id: p.capture_id || "—",
      store_id: "DEMO-S01",
      camera_id: "CAM-S01-A",
      capture_timestamp: p.capture_timestamp || "—",
      capture_source: "CCTV",
      image_filename: p.capture_id ? `${p.capture_id}.jpg` : "—",
      sku_id: p.sku_id,
      sku_name: p.sku_name,
      unit_count: p.unit_count,
      confidence_score: p.confidence_score,
      detection_method: "Visual",
      bounding_box: [],
      is_flagged: p.is_flagged,
      flag_reason: p.is_flagged
        ? p.flag_reason === "Unrecognized"
          ? "Unrecognized"
          : "Low Confidence"
        : "",
      processing_time_ms: p.processing_time_ms || 0,
      image_key: "",
      frame_w: 2560,
      frame_h: 1440,
      faces_blurred: 0,
      pipeline: "long",
    },
    audit: {
      accuracy: null,
      expectedLabel: p.sku_id,
      mismatchType: "None",
      reviewedAt: null,
    },
  };
}

export function CategoryProductsView() {
  const { searchQuery: sidebarSearch } = useSidebarSearch();
  const { isApproved, hasGroup, getIdToken } = useAuth();

  const [products, setProducts] = useState<SkuProduct[]>(SKU_PRODUCTS);
  const [liveMode, setLiveMode] = useState(false);
  const [unrecognizedCount, setUnrecognizedCount] = useState<number>(12);
  const [liveStores, setLiveStores] = useState<ApiStore[] | null>(null);
  const [liveQueue, setLiveQueue] = useState<ApiReviewQueueItem[] | null>(null);
  const [localSearch, setLocalSearch] = useState("");
  const [storeFilter, setStoreFilter] = useState<string>("All stores (30)");
  const [categoryFilter, setCategoryFilter] =
    useState<CategoryFilterOption>("All");
  const [statusFilter, setStatusFilter] = useState<StatusFilterOption>("All");
  const [sortBy, setSortBy] = useState<SortOption>(
    "On-shelf stock (high → low)"
  );

  // Match Figma: first 2 rows pre-selected
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(SKU_PRODUCTS.filter((p) => p.defaultSelected).map((p) => p.id))
  );

  const [viewingProduct, setViewingProduct] = useState<SkuProduct | null>(null);
  const [reviewQueueOpen, setReviewQueueOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [openRowMenuId, setOpenRowMenuId] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const rowMenuRef = useRef<HTMLDivElement>(null);

  const loadLiveData = React.useCallback(async () => {
    if (!isApproved) {
      setLiveMode(false);
      setLiveStores(null);
      setLiveQueue(null);
      setProducts(SKU_PRODUCTS);
      setUnrecognizedCount(12);
      setStoreFilter("All stores (30)");
      return;
    }
    try {
      const api = createApiClient(getIdToken);
      const [prodRes, storeRes, queueRes] = await Promise.all([
        api.getProducts(),
        api.getStores(),
        api.getReviewQueue(),
      ]);
      const mapped = prodRes.items.map(mapApiProductToSkuProduct);
      setProducts(mapped);
      setLiveStores(storeRes.items);
      setLiveQueue(queueRes.items);
      setUnrecognizedCount(prodRes.unrecognized_units);
      setStoreFilter(`All stores (${storeRes.total})`);
      setSelectedIds(new Set());
      setLiveMode(true);
    } catch {
      // keep preview state on error
    }
  }, [isApproved, getIdToken]);

  useEffect(() => {
    void loadLiveData();
  }, [loadLiveData]);

  const storeDropdownOptions = useMemo(() => {
    if (!liveStores) return CATEGORY_STORE_OPTIONS;
    return [
      `All stores (${liveStores.length})`,
      ...liveStores.map((s) => `${s.store_id} — ${s.store_name}`),
    ];
  }, [liveStores]);

  const categoryDropdownOptions = useMemo<CategoryFilterOption[]>(() => {
    return liveMode
      ? ["All", "Milk", "Snack", "Noodles"]
      : CATEGORY_FILTER_OPTIONS;
  }, [liveMode]);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (
        rowMenuRef.current &&
        !rowMenuRef.current.contains(e.target as Node)
      ) {
        setOpenRowMenuId(null);
      }
    }
    if (openRowMenuId) document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [openRowMenuId]);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2400);
  };

  const filteredProducts = useMemo(() => {
    const q = (localSearch || sidebarSearch).trim().toLowerCase();

    const list = products.filter((item) => {
      if (
        !storeFilter.startsWith("All stores") &&
        !storeFilter.startsWith(item.storeRegion) &&
        item.storeRegion !== storeFilter
      ) {
        return false;
      }
      if (
        categoryFilter !== "All" &&
        item.primaryCategory !== categoryFilter
      ) {
        return false;
      }
      if (statusFilter !== "All" && item.status !== statusFilter) {
        return false;
      }
      if (
        q &&
        !item.name.toLowerCase().includes(q) &&
        !item.skuCode.toLowerCase().includes(q) &&
        !item.modelAlias.toLowerCase().includes(q) &&
        !item.barcode.toLowerCase().includes(q) &&
        !item.categories.some((c) => c.toLowerCase().includes(q))
      ) {
        return false;
      }
      return true;
    });

    return [...list].sort((a, b) => {
      switch (sortBy) {
        case "On-shelf stock (high → low)":
          return b.onShelfStock - a.onShelfStock;
        case "On-shelf stock (low → high)":
          return a.onShelfStock - b.onShelfStock;
        case "Confidence (high → low)":
          return b.confidence - a.confidence;
        case "Name (A → Z)":
          return a.name.localeCompare(b.name);
      }
    });
  }, [
    products,
    localSearch,
    sidebarSearch,
    storeFilter,
    categoryFilter,
    statusFilter,
    sortBy,
  ]);

  const allVisibleSelected =
    filteredProducts.length > 0 &&
    filteredProducts.every((p) => selectedIds.has(p.id));

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        filteredProducts.forEach((p) => next.delete(p.id));
      } else {
        filteredProducts.forEach((p) => next.add(p.id));
      }
      return next;
    });
  };

  const toggleSelectRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleExportCsv = async (rows?: SkuProduct[]) => {
    // When authenticated in live mode and exporting full table, download directly from AWS API
    if (liveMode && !rows) {
      try {
        const api = createApiClient(getIdToken);
        const csvText = await api.exportCvOutputCsv();
        const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "cv-output.csv";
        link.click();
        URL.revokeObjectURL(url);
        showToast("Downloaded live CV Output CSV (16 cols, UTF-8 BOM) from AWS");
        return;
      } catch (err) {
        showToast(
          err instanceof Error ? err.message : "Failed to export CSV from AWS"
        );
        return;
      }
    }
    const targetRows = rows ?? filteredProducts;
    // Exact 16-column Datagent CV Output format with UTF-8 BOM for Vietnamese Excel support
    const header = [
      "reading_id",
      "capture_id",
      "store_id",
      "camera_id",
      "capture_timestamp",
      "capture_source",
      "image_filename",
      "sku_id",
      "sku_name",
      "unit_count",
      "confidence_score",
      "detection_method",
      "bounding_box",
      "is_flagged",
      "flag_reason",
      "processing_time_ms",
    ];
    const body = targetRows.map((p) => {
      const cv = p.cvOutput;
      return [
        cv.reading_id,
        cv.capture_id,
        cv.store_id,
        cv.camera_id,
        cv.capture_timestamp,
        cv.capture_source,
        cv.image_filename,
        cv.sku_id ?? "",
        cv.sku_name ?? "",
        cv.unit_count,
        cv.confidence_score.toFixed(2),
        cv.detection_method,
        JSON.stringify(cv.bounding_box),
        cv.is_flagged ? "TRUE" : "FALSE",
        cv.flag_reason,
        cv.processing_time_ms,
      ];
    });
    const csv =
      "\uFEFF" +
      [header, ...body]
        .map((r) =>
          r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")
        )
        .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "cv-output.csv";
    link.click();
    URL.revokeObjectURL(url);
    showToast(
      `Exported ${targetRows.length} CV Output rows (16 cols, UTF-8 BOM)`
    );
  };

  const handleOpenProductDetails = async (item: SkuProduct) => {
    setViewingProduct(item);
    if (!liveMode) return;
    try {
      const api = createApiClient(getIdToken);
      const detail = await api.getProductDetail(item.id);
      setViewingProduct((curr) => {
        if (!curr || curr.id !== item.id) return curr;
        return {
          ...curr,
          cvOutput: {
            ...curr.cvOutput,
            reading_id: detail.cv_output.reading_id || curr.cvOutput.reading_id,
            capture_id: detail.cv_output.capture_id || curr.cvOutput.capture_id,
            store_id: detail.cv_output.store_id || curr.cvOutput.store_id,
            camera_id: detail.cv_output.camera_id || curr.cvOutput.camera_id,
            capture_timestamp:
              detail.cv_output.capture_timestamp ||
              curr.cvOutput.capture_timestamp,
            image_filename:
              detail.cv_output.image_filename || curr.cvOutput.image_filename,
            image_key: detail.cv_output.image_key || curr.cvOutput.image_key,
            bounding_box: detail.cv_output.bounding_box || [],
            faces_blurred: detail.cv_output.faces_blurred || 0,
          },
          audit: {
            accuracy:
              detail.validation.accuracy !== null
                ? `${detail.validation.accuracy}%`
                : null,
            expectedLabel: detail.validation.expected_label || curr.id,
            mismatchType: detail.validation.mismatch_type || "None",
            reviewedAt: detail.validation.reviewed_at,
          },
        };
      });
    } catch {
      // keep summary modal open
    }
  };

  const handleSaveAudit = async (
    productId: string,
    payload: { expectedLabel: string; mismatchType: string }
  ) => {
    if (liveMode) {
      if (!hasGroup("field_team", "team_admin")) {
        showToast("Only field_team or team_admin can submit corrections.");
        return;
      }
      try {
        const api = createApiClient(getIdToken);
        const prod = products.find((p) => p.id === productId);
        await api.submitCorrection({
          store_id: prod?.cvOutput.store_id || "DEMO-S01",
          reading_id: prod?.cvOutput.reading_id,
          capture_id: prod?.cvOutput.capture_id,
          sku_id: productId,
          corrected_sku_id: payload.expectedLabel,
          correction_type: payload.mismatchType,
          action: "correct",
        });
        showToast("Saved correction to AWS DynamoDB (corrections)");
        void loadLiveData();
      } catch (err) {
        showToast(
          err instanceof Error ? err.message : "Failed to save correction"
        );
        return;
      }
    }
    setProducts((prev) =>
      prev.map((item) =>
        item.id === productId
          ? {
              ...item,
              status: "Validated",
              audit: {
                ...item.audit,
                expectedLabel: payload.expectedLabel,
                mismatchType: payload.mismatchType,
                reviewedAt: new Date().toISOString(),
              },
            }
          : item
      )
    );
    if (!liveMode) {
      showToast("Saved correction to audit state");
    }
  };

  const toggleStockSort = () => {
    setSortBy((prev) =>
      prev === "On-shelf stock (high → low)"
        ? "On-shelf stock (low → high)"
        : "On-shelf stock (high → low)"
    );
  };

  return (
    <div className="min-h-full w-full bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-[1640px] px-4 pt-[26px] pb-10 sm:px-6 lg:px-7">
        {/* Page Header */}
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-black/10 pb-[16px]">
          <div>
            <h1 className="text-[22px] font-normal leading-tight text-black">
              Products
            </h1>
            <p className="mt-[4px] text-[12px] font-normal text-[#6B7280]">
              {liveMode
                ? `Live AWS Singapore backend · ${products.length} SKUs synced (UTC+7)`
                : "View recent products in stores · sample preview mode (UTC+7)"}
            </p>
          </div>

          <button
            type="button"
            onClick={() => handleExportCsv()}
            className="flex h-[36px] items-center gap-[8px] rounded-[8px] border border-[#E5E7EB] bg-white pl-[14px] pr-[16px] text-[13px] font-medium text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
          >
            <Download className="h-[15px] w-[15px]" strokeWidth={1.9} />
            <span>Export CV Output</span>
          </button>
        </header>

        {/* Toolbar */}
        <section
          aria-label="Product toolbar"
          className="mt-[16px] flex flex-wrap items-center justify-between gap-2.5"
        >
          <button
            type="button"
            onClick={() => setImportModalOpen(true)}
            className="flex h-[36px] items-center gap-[8px] rounded-[8px] bg-[#EE730A] pl-[14px] pr-[16px] text-[13px] font-semibold text-white hover:bg-[#D96504] transition-colors cursor-pointer"
          >
            <Upload className="h-[15px] w-[15px]" strokeWidth={2.1} />
            <span>Import SKU Master</span>
          </button>

          <div className="flex flex-wrap items-center gap-[8px]">
            {/* Search input */}
            <div className="flex h-[36px] w-full items-center gap-[8px] rounded-[8px] border border-[#E5E7EB] bg-white px-[12px] focus-within:border-[#EE730A]/60 sm:w-[270px]">
              <Search
                className="h-[15px] w-[15px] shrink-0 text-[#9CA3AF]"
                strokeWidth={1.8}
              />
              <input
                type="text"
                value={localSearch}
                onChange={(e) => setLocalSearch(e.target.value)}
                placeholder="Search name, SKU code or barcode"
                className="min-w-0 flex-1 bg-transparent text-[12px] font-normal text-[#111827] placeholder:text-[#9CA3AF] outline-none"
              />
              {localSearch && (
                <button
                  type="button"
                  onClick={() => setLocalSearch("")}
                  aria-label="Clear search"
                  className="text-[#9CA3AF] hover:text-[#374151] cursor-pointer"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <ToolbarDropdown
              label="Store:"
              value={storeFilter}
              options={storeDropdownOptions}
              onChange={setStoreFilter}
            />
            <ToolbarDropdown
              label="Category:"
              value={categoryFilter}
              options={categoryDropdownOptions}
              onChange={setCategoryFilter}
            />
            <ToolbarDropdown
              label="Status:"
              value={statusFilter}
              options={STATUS_FILTER_OPTIONS}
              onChange={setStatusFilter}
            />
            <ToolbarDropdown
              label="Sort:"
              value={sortBy}
              options={SORT_OPTIONS}
              onChange={setSortBy}
            />
          </div>
        </section>

        {/* Unmatched Products Warning Banner */}
        <div className="mt-[16px] flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-[#FED7AA] bg-[#FFF7ED] py-[10px] pl-[14px] pr-[16px]">
          <div className="flex items-center gap-[10px]">
            <AlertTriangle
              className="h-[16px] w-[16px] shrink-0 text-[#C2560A]"
              strokeWidth={1.9}
            />
            <p className="text-[13px] font-normal text-[#7C2D12]">
              {unrecognizedCount}{" "}
              {unrecognizedCount === 1
                ? "unrecognized unit was"
                : "unrecognized units were"}{" "}
              seen on shelves in recent captures but matched no SKU (sku_id =
              NULL), so they are excluded from this list.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setReviewQueueOpen(true)}
            className="inline-flex items-center gap-1 text-[13px] font-semibold text-[#C2560A] hover:underline cursor-pointer"
          >
            <span>Open review queue</span>
            <ArrowRight className="h-[14px] w-[14px]" strokeWidth={2.2} />
          </button>
        </div>

        {/* SKU Table (Horizontal scroll wrapper for narrow viewports) */}
        <section aria-label="SKU product list" className="mt-[16px] overflow-x-auto pb-2">
          <div className="min-w-[1080px]">
            {/* Table Header */}
            <div className="flex h-[32px] items-center px-[16px] text-[11px] font-semibold tracking-[0.036em] text-[#6B7280] uppercase">
              <div className="w-[32px] shrink-0 flex items-center">
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={allVisibleSelected}
                  aria-label="Select all products"
                  onClick={toggleSelectAll}
                  className={`flex h-[16px] w-[16px] items-center justify-center rounded-[4px] transition-colors cursor-pointer ${
                    allVisibleSelected
                      ? "bg-[#515151] text-white"
                      : "border-[1.5px] border-[#D1D5DB] bg-white hover:border-[#9CA3AF]"
                  }`}
                >
                  {allVisibleSelected && (
                    <Check className="h-[11px] w-[11px]" strokeWidth={3} />
                  )}
                </button>
              </div>
              <div className="flex-[2.4] min-w-[240px] pr-[12px]">PRODUCT</div>
              <div className="w-[126px] shrink-0 pr-[12px]">CATEGORY</div>
              <div className="w-[82px] shrink-0 pr-[12px]">PACK</div>
              <div className="w-[152px] shrink-0 pr-[12px]">SKU CODE</div>
              <div className="w-[140px] shrink-0 pr-[12px]">
                <button
                  type="button"
                  onClick={toggleStockSort}
                  className="inline-flex items-center gap-1 uppercase hover:text-[#111827] transition-colors cursor-pointer"
                >
                  <span>ON-SHELF STOCK</span>
                  {sortBy === "On-shelf stock (low → high)" ? (
                    <ArrowUp className="h-[12px] w-[12px]" strokeWidth={2.2} />
                  ) : (
                    <ArrowDown className="h-[12px] w-[12px]" strokeWidth={2.2} />
                  )}
                </button>
              </div>
              <div className="w-[140px] shrink-0 pr-[12px]">
                <button
                  type="button"
                  onClick={() => setSortBy("Confidence (high → low)")}
                  className="uppercase hover:text-[#111827] transition-colors cursor-pointer"
                >
                  CONFIDENCE
                </button>
              </div>
              <div className="w-[128px] shrink-0 pr-[12px]">
                AVAIL IN STORES
              </div>
              <div className="w-[90px] shrink-0 text-right">ACTIONS</div>
            </div>

            {/* Table Rows */}
            <div className="mt-[8px] flex flex-col gap-[8px]">
              {filteredProducts.length === 0 ? (
                <div className="flex h-[140px] items-center justify-center rounded-[10px] border border-[#EFF0F6] bg-white text-[13px] text-[#6B7280]">
                  No products match the current search and filter criteria.
                </div>
              ) : (
                filteredProducts.map((item) => {
                  const isSelected = selectedIds.has(item.id);
                  const barWidthPct = Math.min(
                    100,
                    Math.max(12, Math.round(item.confidence * 100))
                  );
                  const barColor = getConfidenceColor(item.confidence);

                  return (
                    <div
                      key={item.id}
                      className={`flex min-h-[72px] items-center rounded-[10px] bg-white px-[16px] py-[12px] transition-colors ${
                        isSelected
                          ? "border border-[#969696]"
                          : "border border-[#EFF0F6] hover:border-[#D1D5DB]"
                      }`}
                    >
                      {/* Checkbox */}
                      <div className="w-[32px] shrink-0 flex items-center">
                        <button
                          type="button"
                          role="checkbox"
                          aria-checked={isSelected}
                          aria-label={`Select ${item.name}`}
                          onClick={() => toggleSelectRow(item.id)}
                          className={`flex h-[16px] w-[16px] items-center justify-center rounded-[4px] transition-colors cursor-pointer ${
                            isSelected
                              ? "bg-[#515151] text-white"
                              : "border-[1.5px] border-[#D1D5DB] bg-white hover:border-[#9CA3AF]"
                          }`}
                        >
                          {isSelected && (
                            <Check
                              className="h-[11px] w-[11px]"
                              strokeWidth={3}
                            />
                          )}
                        </button>
                      </div>

                      {/* Product Thumbnail + Name */}
                      <div className="flex flex-[2.4] min-w-[240px] items-center gap-[12px] pr-[12px]">
                        <div className="relative h-[44px] w-[44px] shrink-0 overflow-hidden rounded-[10px] border border-black/15 bg-white shadow-[-2px_3px_4px_rgba(0,0,0,0.16)]">
                          <Image
                            src={item.thumbnail}
                            alt={item.name}
                            width={44}
                            height={44}
                            className="h-full w-full object-cover"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => void handleOpenProductDetails(item)}
                          className="line-clamp-2 text-left text-[13px] font-semibold leading-[18px] text-[#111827] hover:text-[#EE730A] transition-colors cursor-pointer"
                        >
                          {item.name}
                        </button>
                      </div>

                      {/* Category Pills */}
                      <div className="flex w-[126px] shrink-0 flex-wrap items-center gap-[4px] pr-[12px]">
                        {item.categories.map((tag) => (
                          <span
                            key={tag}
                            className="rounded-[6px] bg-[#F3F4F6] px-[8px] py-[3px] text-[11px] font-medium leading-tight text-[#374151]"
                          >
                            {tag}
                          </span>
                        ))}
                        {item.hasMoreCategories && (
                          <span className="rounded-[6px] bg-[#F3F4F6] px-[6px] py-[3px] text-[11px] font-medium leading-tight text-[#374151]">
                            ...
                          </span>
                        )}
                      </div>

                      {/* Pack */}
                      <div className="flex w-[82px] shrink-0 flex-col gap-[2px] pr-[12px]">
                        <span className="text-[13px] font-medium leading-tight text-[#111827]">
                          {item.packType}
                        </span>
                        <span className="text-[12px] font-normal leading-tight text-[#6B7280]">
                          {item.packSize}
                        </span>
                      </div>

                      {/* SKU Code + Barcode */}
                      <div className="flex w-[152px] shrink-0 flex-col gap-[2px] pr-[12px]">
                        <span className="text-[12px] font-medium leading-tight text-[#111827]">
                          {item.skuCode}
                        </span>
                        <span className="text-[11px] font-normal leading-tight text-[#9CA3AF]">
                          {item.barcode}
                        </span>
                      </div>

                      {/* On-Shelf Stock */}
                      <div className="flex w-[140px] shrink-0 items-baseline gap-[4px] pr-[12px]">
                        <span className="text-[15px] font-semibold text-[#111827]">
                          {item.onShelfStock}
                        </span>
                        <span className="text-[12px] font-normal text-[#6B7280]">
                          units
                        </span>
                      </div>

                      {/* Confidence + Progress Bar (fixed format: 93% instead of 0.93 %) */}
                      <div
                        className="flex w-[140px] shrink-0 flex-col gap-[6px] pr-[12px]"
                        title={`confidence_score: ${item.confidence.toFixed(2)} · is_flagged: ${item.cvOutput.is_flagged ? "TRUE" : "FALSE"}`}
                      >
                        <div className="flex items-center gap-[6px]">
                          <span className="text-[13px] font-semibold leading-none text-[#111827]">
                            {Math.round(item.confidence * 100)}%
                          </span>
                          {item.cvOutput.is_flagged && (
                            <span className="rounded bg-[#FFF7ED] px-1.5 py-[1px] text-[10px] font-semibold text-[#C2560A]">
                              Flagged
                            </span>
                          )}
                        </div>
                        <div className="h-[4px] w-[72px] overflow-hidden rounded-[2px] bg-[#EEF0F3]">
                          <div
                            className="h-full rounded-[2px]"
                            style={{
                              width: `${barWidthPct}%`,
                              backgroundColor: barColor,
                            }}
                          />
                        </div>
                      </div>

                      {/* Avail In Stores */}
                      <div className="flex w-[128px] shrink-0 items-baseline gap-[1px] pr-[12px]">
                        <span className="text-[18px] font-semibold leading-none text-[#111827]">
                          {item.storesAvailable}
                        </span>
                        <span className="text-[12px] font-normal leading-none text-[#6B7280]">
                          /{item.storesTotal} stores
                        </span>
                      </div>

                      {/* Actions */}
                      <div className="relative flex w-[90px] shrink-0 items-center justify-end gap-[6px]">
                        <button
                          type="button"
                          onClick={() => void handleOpenProductDetails(item)}
                          className="flex h-[28px] items-center rounded-[6px] border border-[#E5E7EB] bg-white px-[12px] text-[12px] font-medium text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
                        >
                          View
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setOpenRowMenuId((prev) =>
                              prev === item.id ? null : item.id
                            )
                          }
                          aria-label={`More actions for ${item.name}`}
                          className="flex h-[28px] w-[28px] items-center justify-center rounded-[6px] border border-[#E5E7EB] bg-white text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
                        >
                          <MoreHorizontal className="h-[15px] w-[15px]" />
                        </button>

                        {openRowMenuId === item.id && (
                          <div
                            ref={rowMenuRef}
                            className="absolute right-0 top-[34px] z-20 w-[160px] rounded-[10px] border border-[#E5E7EB] bg-white p-1 shadow-[0_8px_22px_rgba(0,0,0,0.08)]"
                          >
                            <button
                              type="button"
                              onClick={() => {
                                setOpenRowMenuId(null);
                                setViewingProduct(item);
                              }}
                              className="flex w-full rounded-[7px] px-2.5 py-1.5 text-left text-[12px] text-[#111827] hover:bg-[#F7F8FA] cursor-pointer"
                            >
                              View Validation Details
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setOpenRowMenuId(null);
                                navigator.clipboard?.writeText(item.skuCode);
                                showToast(`Copied ${item.skuCode}`);
                              }}
                              className="flex w-full rounded-[7px] px-2.5 py-1.5 text-left text-[12px] text-[#111827] hover:bg-[#F7F8FA] cursor-pointer"
                            >
                              Copy SKU Code
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setOpenRowMenuId(null);
                                handleExportCsv([item]);
                              }}
                              className="flex w-full rounded-[7px] px-2.5 py-1.5 text-left text-[12px] text-[#111827] hover:bg-[#F7F8FA] cursor-pointer"
                            >
                              Export Row CSV
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>
      </div>

      {/* Product Details / Validation Card Modal (aligned with CV Output 16-col spec) */}
      <ProductDetailsModal
        key={viewingProduct?.id ?? "closed"}
        product={viewingProduct}
        onClose={() => setViewingProduct(null)}
        onSaveAudit={handleSaveAudit}
      />

      {/* Unmatched / Flagged Review Queue Modal */}
      {reviewQueueOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
          onClick={() => setReviewQueueOpen(false)}
        >
          <div
            className="w-full max-w-[660px] overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_10px_28px_rgba(0,0,0,0.14)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#EFF0F6] px-5 py-4">
              <div>
                <h3 className="text-[16px] font-semibold text-[#111827]">
                  Flagged &amp; Unmatched Review Queue
                </h3>
                <p className="text-[12px] text-[#6B7280]">
                  Rows with is_flagged = TRUE (confidence &lt; 0.70 or sku_id =
                  NULL) ready for Datagent review
                </p>
              </div>
              <button
                type="button"
                onClick={() => setReviewQueueOpen(false)}
                aria-label="Close review queue"
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827] cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto divide-y divide-[#EFF0F6] px-5 py-2">
              {liveMode && liveQueue ? (
                liveQueue.length === 0 ? (
                  <p className="py-6 text-center text-[13px] text-[#6B7280]">
                    No flagged rows waiting in the AWS review queue.
                  </p>
                ) : (
                  liveQueue.map((det) => (
                    <div
                      key={det.queue_key}
                      className="flex flex-wrap items-center justify-between gap-4 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-[#FFF7ED] px-2 py-0.5 text-[10.5px] font-semibold text-[#C2560A]">
                            {det.flag_reason}
                          </span>
                          <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[10.5px] font-medium text-[#374151]">
                            {det.status}
                          </span>
                          <span className="font-mono text-[11.5px] text-[#374151]">
                            {det.reading_id}
                          </span>
                        </div>
                        <p className="mt-1 truncate text-[12.5px] font-medium text-[#111827]">
                          {det.sku_name || det.sku_id} ({det.unit_count}{" "}
                          {det.unit_count === 1 ? "unit" : "units"})
                        </p>
                        <p className="mt-0.5 text-[11.5px] text-[#6B7280]">
                          {det.store_id} &middot; {det.camera_id} &middot; conf{" "}
                          {Number(det.confidence_score).toFixed(2)}
                          {det.frame_presigned_url && (
                            <>
                              {" "}
                              &middot;{" "}
                              <a
                                href={det.frame_presigned_url}
                                target="_blank"
                                rel="noreferrer"
                                className="font-medium text-[#0051C3] hover:underline"
                              >
                                View blurred frame (15m URL)
                              </a>
                            </>
                          )}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!hasGroup("field_team", "team_admin")) {
                            showToast(
                              "Only field_team or team_admin can confirm review items."
                            );
                            return;
                          }
                          try {
                            const api = createApiClient(getIdToken);
                            await api.submitCorrection({
                              store_id: det.store_id,
                              queue_key: det.queue_key,
                              reading_id: det.reading_id,
                              capture_id: det.capture_id,
                              sku_id: det.sku_id,
                              action: "confirm",
                            });
                            showToast(`Confirmed ${det.reading_id} (Đã xác nhận)`);
                            void loadLiveData();
                          } catch (err) {
                            showToast(
                              err instanceof Error
                                ? err.message
                                : "Action failed"
                            );
                          }
                        }}
                        className="shrink-0 rounded-[6px] border border-[#E5E7EB] px-2.5 py-1 text-[12px] font-medium text-[#111827] hover:bg-[#F9FAFB] cursor-pointer"
                      >
                        Confirm AI
                      </button>
                    </div>
                  ))
                )
              ) : (
                UNMATCHED_REVIEW_QUEUE.map((det) => (
                  <div
                    key={det.id}
                    className="flex flex-wrap items-center justify-between gap-4 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-full bg-[#FFF7ED] px-2 py-0.5 text-[10.5px] font-semibold text-[#C2560A]">
                          {det.flag_reason}
                        </span>
                        <span className="font-mono text-[11.5px] text-[#374151]">
                          {det.reading_id}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-[12.5px] font-medium text-[#111827]">
                        Suggested: {det.suggestedSku} ({det.unit_count}{" "}
                        {det.unit_count === 1 ? "unit" : "units"})
                      </p>
                      <p className="mt-0.5 text-[11.5px] text-[#6B7280]">
                        {det.storeName} &middot; {det.camera_id} &middot; conf{" "}
                        {det.confidence_score.toFixed(2)} &middot; box{" "}
                        <span className="font-mono">
                          {JSON.stringify(det.bounding_box[0])}
                        </span>
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        showToast(
                          `Mapped ${det.reading_id} → ${det.suggestedSku}`
                        );
                      }}
                      className="shrink-0 rounded-[6px] border border-[#E5E7EB] px-2.5 py-1 text-[12px] font-medium text-[#111827] hover:bg-[#F9FAFB] cursor-pointer"
                    >
                      Map SKU
                    </button>
                  </div>
                ))
              )}
            </div>
            <div className="flex justify-end border-t border-[#EFF0F6] px-5 py-3">
              <button
                type="button"
                onClick={() => setReviewQueueOpen(false)}
                className="rounded-[8px] bg-[#F3F4F6] px-4 py-1.5 text-[13px] font-medium text-[#111827] hover:bg-[#E5E7EB] cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import SKU Master Modal */}
      {importModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
          onClick={() => setImportModalOpen(false)}
        >
          <div
            className="w-full max-w-[480px] rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_10px_28px_rgba(0,0,0,0.14)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-[16px] font-semibold text-[#111827]">
                Import SKU Master
              </h3>
              <button
                type="button"
                onClick={() => setImportModalOpen(false)}
                aria-label="Close import modal"
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[#6B7280] hover:bg-[#F3F4F6] cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-1 text-[12.5px] text-[#6B7280]">
              Upload a CSV or Excel master catalog containing SKU codes,
              barcodes, pack sizes, and categories.
            </p>
            <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-6 py-8 text-center hover:border-[#EE730A]/60 transition-colors">
              <Upload className="h-6 w-6 text-[#EE730A]" strokeWidth={1.8} />
              <span className="mt-2 text-[13px] font-medium text-[#111827]">
                Click to choose CSV file
              </span>
              <span className="mt-1 text-[11.5px] text-[#6B7280]">
                Supports .csv, .xlsx up to 10MB
              </span>
              <input
                type="file"
                accept=".json,.csv"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  if (!liveMode) {
                    setImportModalOpen(false);
                    showToast(`Imported "${file.name}" (preview mode)`);
                    return;
                  }
                  if (!hasGroup("team_admin")) {
                    setImportModalOpen(false);
                    showToast("Only team_admin can import SKU Master.");
                    return;
                  }
                  try {
                    const text = await file.text();
                    let items: Record<string, unknown>[] = [];
                    if (file.name.toLowerCase().endsWith(".json")) {
                      const parsed = JSON.parse(text);
                      items = Array.isArray(parsed)
                        ? parsed
                        : parsed.items || [];
                    } else {
                      const lines = text.trim().split(/\r?\n/);
                      const headers = lines[0]
                        .replace(/^\uFEFF/, "")
                        .split(",")
                        .map((h) => h.trim().replace(/^"|"$/g, ""));
                      items = lines.slice(1).map((line) => {
                        const vals = line
                          .split(",")
                          .map((v) => v.trim().replace(/^"|"$/g, ""));
                        const obj: Record<string, unknown> = {};
                        headers.forEach((h, idx) => {
                          if (vals[idx] !== "") obj[h] = vals[idx];
                        });
                        return obj;
                      });
                    }
                    const api = createApiClient(getIdToken);
                    await api.importSkuMaster(items);
                    setImportModalOpen(false);
                    showToast(`Imported ${items.length} SKUs into AWS sku_master`);
                    void loadLiveData();
                  } catch (err) {
                    setImportModalOpen(false);
                    showToast(
                      err instanceof Error ? err.message : "SKU import failed"
                    );
                  }
                }}
              />
            </label>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setImportModalOpen(false)}
                className="rounded-[8px] bg-[#F3F4F6] px-4 py-1.5 text-[13px] font-medium text-[#111827] hover:bg-[#E5E7EB] cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Subtle Toast Notification */}
      {toastMsg && (
        <div className="fixed bottom-5 right-16 z-50 rounded-[10px] bg-[#111827] px-4 py-2.5 text-[12.5px] font-medium text-white shadow-lg">
          {toastMsg}
        </div>
      )}
    </div>
  );
}
