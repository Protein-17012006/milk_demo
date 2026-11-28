"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  Search,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import {
  createApiClient,
  type ApiProduct,
  type ApiDisplayStatus,
  type ApiReviewQueueItem,
  type ApiStore,
} from "@/lib/api";
import { LIVE_REFRESH_MS } from "@/lib/config";
import { productThumbnail } from "@/lib/product-thumbnail";
import {
  ALL_STORES_LABEL,
  MILK_FLAG_THRESHOLD,
  NO_BARCODE,
  STATUS_FILTER_OPTIONS,
  categoryColumns,
  emptyProductsText,
  showStoreFilter,
  sortOptions,
  type CategoryFilterOption,
  type PrimaryCategory,
  type SkuProduct,
  type SortOption,
  type StatusFilterOption,
} from "@/lib/products-ui";
import { ExportCsvButton } from "@/components/common/ExportCsvButton";
import { ProductDetailsModal } from "./ProductDetailsModal";
import { ProductRow } from "./ProductRow";
import { ProductGroupRow } from "./ProductGroupRow";
import { ReviewBanner, ReviewQueueDialog } from "./ReviewQueue";
import { cardFromQueueItem, correctionToast, queueKeyForReading } from "@/lib/review-queue";
import { groupProducts, type ProductGroup } from "@/lib/product-groups";
import { displayBanner } from "@/lib/shelf-ui";
import { splitByPlan } from "@/lib/shelf-now";

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

function statusOf(isFlagged: boolean, confidence: number): SkuProduct["status"] {
  if (!isFlagged) return "Not flagged";
  return confidence < MILK_FLAG_THRESHOLD ? "Low Confidence" : "Needs Review";
}

function flagReasonOf(isFlagged: boolean, reason: string): string {
  if (!isFlagged) return "";
  return reason === "Unrecognized" ? "Unrecognized" : "Low Confidence";
}

function mapApiProductToSkuProduct(p: ApiProduct): SkuProduct {
  const catLower = (p.category || "Milk").toLowerCase();
  const primaryCategory: SkuProduct["primaryCategory"] = catLower.includes(
    "noodle"
  )
    ? "Noodles"
    : catLower.includes("snack")
      ? "Snacks"
      : "Milk";

  const status = statusOf(p.is_flagged, p.confidence_score);

  return {
    id: p.sku_id,
    name: p.sku_name,
    modelAlias: p.model_alias || p.sku_id,
    thumbnail: productThumbnail(p.image_url),
    categories: [p.category || "Milk", p.subcategory || p.brand || "SKU"].filter(
      Boolean
    ),
    primaryCategory,
    brand: p.brand,
    subcategory: p.subcategory,
    packType: p.pack_type || "Carton",
    packSize: p.pack_size || "—",
    skuCode: p.model_alias || p.sku_id,
    barcode: p.barcode || NO_BARCODE,
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
    detailFetchedAt: null,
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
      flag_reason: flagReasonOf(p.is_flagged, p.flag_reason),
      processing_time_ms: p.processing_time_ms || 0,
      image_key: "",
      frame_w: 2560,
      frame_h: 1440,
      faces_blurred: 0,
      pipeline: "long",
      frame_url: null,
    },
    audit: {
      accuracy: null,
      expectedLabel: p.sku_id,
      mismatchType: "None",
      reviewedAt: null,
    },
    reliability: p.reliability,
    inShelfPlan: p.in_shelf_plan === true,
    notInView: p.stock_status === "NOT_IN_VIEW",
    notInViewInfo:
      p.stock_status === "NOT_IN_VIEW" && p.not_in_view ? { since: p.not_in_view.since } : undefined,
  };
}

export function CategoryProductsView() {
  const { isApproved, hasGroup, getIdToken } = useAuth();
  // The review queue, corrections and the model's own numbers are the team's tools; a viewer sees stock only.
  const canReview = hasGroup("field_team", "team_admin");

  // Rows exist only once the live API answers; signed out, the table stays empty (no sample rows).
  const [products, setProducts] = useState<SkuProduct[]>([]);
  const [liveMode, setLiveMode] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [unrecognizedCount, setUnrecognizedCount] = useState<number | null>(null);
  const [liveStores, setLiveStores] = useState<ApiStore[] | null>(null);
  const [liveQueue, setLiveQueue] = useState<ApiReviewQueueItem[] | null>(null);
  const [displays, setDisplays] = useState<ApiDisplayStatus[]>([]);
  const [localSearch, setLocalSearch] = useState("");
  const [storeFilter, setStoreFilter] = useState<string>(ALL_STORES_LABEL);
  const [categoryFilter, setCategoryFilter] =
    useState<CategoryFilterOption>("All");
  const [statusFilter, setStatusFilter] = useState<StatusFilterOption>("All");
  const [sortBy, setSortBy] = useState<SortOption>(
    "On-shelf stock (high → low)"
  );

  // Product-line groups start open; keys are stable, so the 15 s refresh keeps the closed ones closed.
  const [collapsedKeys, setCollapsedKeys] = useState<Set<string>>(() => new Set());
  // Products that are not on the store's shelf plan sit in a section of their own, closed until asked for.
  const [offPlanOpen, setOffPlanOpen] = useState(false);

  const [viewingProduct, setViewingProduct] = useState<SkuProduct | null>(null);
  const [reviewQueueOpen, setReviewQueueOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // background = the periodic refresh: update the numbers but keep the user's filter and selection.
  const loadLiveData = React.useCallback(async (opts?: { background?: boolean }) => {
    const background = opts?.background === true;
    if (!isApproved) {
      if (background) return;
      setLiveMode(false);
      setLiveStores(null);
      setLiveQueue(null);
      setDisplays([]);
      setProducts([]);
      setUnrecognizedCount(null);
      setStoreFilter(ALL_STORES_LABEL);
      return;
    }
    try {
      const api = createApiClient(getIdToken);
      const [prodRes, storeRes, queueRes] = await Promise.all([
        api.getProducts(),
        api.getStores(),
        canReview ? api.getReviewQueue() : Promise.resolve(null),
      ]);
      const mapped = prodRes.items.map(mapApiProductToSkuProduct);
      setProducts(mapped);
      setLiveStores(storeRes.items);
      setLiveQueue(queueRes ? queueRes.items : null);
      setDisplays(prodRes.displays ?? []);
      setUnrecognizedCount(prodRes.unrecognized_units);
      if (!background) {
        setStoreFilter(`${ALL_STORES_LABEL} (${storeRes.total})`);
      }
      setLiveMode(true);
      setLoadFailed(false);
    } catch {
      // a failed background refresh keeps the rows on show; a failed first read says so
      if (!background) setLoadFailed(true);
    }
  }, [isApproved, getIdToken, canReview]);

  useEffect(() => {
    void loadLiveData();
  }, [loadLiveData]);

  // Live stock: re-read the API every LIVE_REFRESH_MS while this tab is visible (HOANG-P10 Nextstep 9).
  useEffect(() => {
    if (!isApproved) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void loadLiveData({ background: true });
    }, LIVE_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [isApproved, loadLiveData]);

  const displayLine = useMemo(() => displayBanner(displays), [displays]);

  const storeDropdownOptions = useMemo(() => {
    if (!liveStores) return [ALL_STORES_LABEL];
    return [
      `${ALL_STORES_LABEL} (${liveStores.length})`,
      ...liveStores.map((s) => `${s.store_id} — ${s.store_name}`),
    ];
  }, [liveStores]);

  // Only categories that the live rows actually contain.
  const categoryDropdownOptions = useMemo<CategoryFilterOption[]>(() => {
    const order: PrimaryCategory[] = ["Milk", "Snacks", "Noodles"];
    const present = new Set(products.map((p) => p.primaryCategory));
    return ["All", ...order.filter((c) => present.has(c))];
  }, [products]);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2400);
  };

  const filteredProducts = useMemo(() => {
    const q = localSearch.trim().toLowerCase();

    const list = products.filter((item) => {
      if (
        !storeFilter.startsWith(ALL_STORES_LABEL) &&
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
          return (b.notInView ? 0 : b.onShelfStock) - (a.notInView ? 0 : a.onShelfStock);
        case "On-shelf stock (low → high)":
          return (a.notInView ? 0 : a.onShelfStock) - (b.notInView ? 0 : b.onShelfStock);
        case "Confidence (high → low)":
          return b.confidence - a.confidence;
        case "Name (A → Z)":
          return a.name.localeCompare(b.name);
      }
    });
  }, [
    products,
    localSearch,
    storeFilter,
    categoryFilter,
    statusFilter,
    sortBy,
  ]);

  const searchText = localSearch.trim();
  // With a shelf plan, its products come first; a store without one (no product is on a plan) lists all as before.
  const hasPlan = useMemo(() => products.some((p) => p.inShelfPlan), [products]);
  const { onPlan, offPlan } = useMemo(() => splitByPlan(filteredProducts), [filteredProducts]);
  const mainGroups = useMemo(
    () => groupProducts(hasPlan ? onPlan : filteredProducts, sortBy),
    [hasPlan, onPlan, filteredProducts, sortBy]
  );
  const offPlanGroups = useMemo(() => (hasPlan ? groupProducts(offPlan, sortBy) : []), [hasPlan, offPlan, sortBy]);
  const groups = useMemo(() => [...mainGroups, ...offPlanGroups], [mainGroups, offPlanGroups]);
  const showOffPlan = offPlanOpen || searchText !== "";
  const isExpanded = (key: string) => searchText !== "" || !collapsedKeys.has(key);
  const allGroupsExpanded = groups.length > 0 && groups.every((g) => !collapsedKeys.has(g.key));

  const toggleAllGroups = () => {
    setCollapsedKeys(allGroupsExpanded ? new Set(groups.map((g) => g.key)) : new Set());
  };

  const toggleGroup = (key: string) => {
    setCollapsedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const emptyText = emptyProductsText({ approved: isApproved, loaded: liveMode, failed: loadFailed });
  const storeCount = liveStores?.length ?? 0;
  const columns = categoryColumns(canReview, storeCount);
  // the product column (240) and the padding (32), plus every fixed column on show
  const tableMinWidth =
    240 + 32 + 126 + 82 + 140 + 64 + (columns.skuCode ? 152 : 0) + (columns.confidence ? 140 : 0) + (columns.stores ? 128 : 0);


  // Fetches GET /products/{sku} into the open card; returns the reading id it now shows (null on failure).
  const loadProductDetail = async (item: SkuProduct): Promise<string | null> => {
    if (!liveMode) return null;
    try {
      const api = createApiClient(getIdToken);
      const detail = await api.getProductDetail(item.id);
      setViewingProduct((curr) => {
        if (!curr || curr.id !== item.id) return curr;
        // Every number on the card comes from the reading the detail call returned: captures arrive
        // every few seconds, so mixing it with the list row would show one reading's count next to
        // another reading's boxes.
        const cv = detail.cv_output;
        return {
          ...curr,
          status: statusOf(cv.is_flagged, cv.confidence_score),
          detailFetchedAt: Date.now(),
          cvOutput: {
            ...curr.cvOutput,
            unit_count: cv.unit_count,
            confidence_score: cv.confidence_score,
            is_flagged: cv.is_flagged,
            flag_reason: flagReasonOf(cv.is_flagged, cv.flag_reason),
            processing_time_ms: cv.processing_time_ms || curr.cvOutput.processing_time_ms,
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
            frame_url: cv.frame_presigned_url,
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
      return detail.cv_output.reading_id;
    } catch {
      // keep summary modal open
      return null;
    }
  };

  const handleOpenProductDetails = async (item: SkuProduct) => {
    setViewingProduct(item);
    await loadProductDetail(item);
  };

  // "Correct" in the review queue: the card opens on the flagged reading itself (not on the product's latest one),
  // in place of the queue; closing the card brings the queue back.
  const openQueueCorrection = (det: ApiReviewQueueItem) => {
    setReviewQueueOpen(false);
    setViewingProduct(cardFromQueueItem(det, products.find((p) => p.id === det.sku_id), Date.now()));
  };

  // A fresh signed frame link for a card opened from the queue: its reading comes from the queue, not from
  // GET /products/{sku}. A newer doubtful reading may have taken the item over; the card then shows that one.
  const refreshQueueCard = async (queueKey: string): Promise<string | null> => {
    try {
      const queue = await createApiClient(getIdToken).getReviewQueue();
      setLiveQueue(queue.items);
      const det = queue.items.find((item) => item.queue_key === queueKey);
      if (!det) return null;
      setViewingProduct((curr) =>
        curr?.reviewQueueKey === queueKey
          ? cardFromQueueItem(det, products.find((p) => p.id === det.sku_id), Date.now())
          : curr
      );
      return det.reading_id;
    } catch {
      return null;
    }
  };

  const closeCard = () => {
    const fromQueue = Boolean(viewingProduct?.reviewQueueKey);
    setViewingProduct(null);
    if (fromQueue) setReviewQueueOpen(true);
  };

  /** Saves the card's correction; resolves to whether it was saved (the card says "Saved" only then). */
  const handleSaveAudit = async (
    productId: string,
    payload: { expectedLabel: string; mismatchType: string }
  ): Promise<boolean> => {
    if (liveMode) {
      if (!hasGroup("field_team", "team_admin")) {
        showToast("Your account cannot save corrections.");
        return false;
      }
      try {
        const api = createApiClient(getIdToken);
        // the reading on the open card: the list row may already hold a newer one
        const card = viewingProduct?.id === productId ? viewingProduct : products.find((p) => p.id === productId);
        // the queue item this correction answers: the one the card was opened from, or the waiting item of the
        // very reading the card shows. With its key the backend marks it "Đã sửa".
        const queueKey = card?.reviewQueueKey ?? queueKeyForReading(liveQueue ?? [], card?.cvOutput.reading_id);
        const saved = await api.submitCorrection({
          store_id: card?.cvOutput.store_id || "DEMO-S01",
          queue_key: queueKey,
          reading_id: card?.cvOutput.reading_id,
          capture_id: card?.cvOutput.capture_id,
          sku_id: productId,
          corrected_sku_id: payload.expectedLabel,
          correction_type: payload.mismatchType,
          discrepancy_category: payload.mismatchType,
          action: "correct",
        });
        showToast(correctionToast(Boolean(queueKey), saved.label_request));
        void loadLiveData();
      } catch (err) {
        showToast(
          err instanceof Error ? err.message : "Failed to save correction"
        );
        return false;
      }
    }
    const reviewed = (item: SkuProduct): SkuProduct => ({
      ...item,
      status: "Not flagged",
      audit: {
        ...item.audit,
        expectedLabel: payload.expectedLabel,
        mismatchType: payload.mismatchType,
        reviewedAt: new Date().toISOString(),
      },
    });
    setViewingProduct((curr) => (curr?.id === productId ? reviewed(curr) : curr));
    // a card opened from the queue reviewed an older reading: the product's row keeps its latest one as it is
    if (!viewingProduct?.reviewQueueKey) {
      setProducts((prev) => prev.map((item) => (item.id === productId ? reviewed(item) : item)));
    }
    if (!liveMode) {
      showToast("Saved the correction.");
    }
    return true;
  };

  // "Confirm reading" on a card opened from the review queue: nothing was changed, so its item becomes "Đã xác nhận".
  const confirmCard = async (): Promise<boolean> => {
    const card = viewingProduct;
    if (!card?.reviewQueueKey) return false;
    if (!hasGroup("field_team", "team_admin")) {
      showToast("Your account cannot confirm readings.");
      return false;
    }
    try {
      const api = createApiClient(getIdToken);
      await api.submitCorrection({
        store_id: card.cvOutput.store_id || "DEMO-S01",
        queue_key: card.reviewQueueKey,
        reading_id: card.cvOutput.reading_id,
        capture_id: card.cvOutput.capture_id,
        sku_id: card.id,
        action: "confirm",
      });
      showToast(`Confirmed ${card.cvOutput.sku_name ?? card.name}`);
      void loadLiveData();
      return true;
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Could not confirm this reading");
      return false;
    }
  };

  // "Confirm AI" in the review queue: the reading was right, so its item becomes "Đã xác nhận".
  const confirmQueueItem = async (det: ApiReviewQueueItem) => {
    if (!hasGroup("field_team", "team_admin")) {
      showToast("Your account cannot confirm readings.");
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
      showToast(`Confirmed ${det.sku_name || det.sku_id}`);
      void loadLiveData();
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Could not confirm this reading");
    }
  };

  const toggleStockSort = () => {
    setSortBy((prev) =>
      prev === "On-shelf stock (high → low)"
        ? "On-shelf stock (low → high)"
        : "On-shelf stock (high → low)"
    );
  };

  const renderGroup = (group: ProductGroup) => (
    <React.Fragment key={group.key}>
      <ProductGroupRow
        group={group}
        expanded={isExpanded(group.key)}
        columns={columns}
        onToggleExpand={() => toggleGroup(group.key)}
      />
      {isExpanded(group.key) &&
        group.variants.map((item) => (
          <ProductRow
            key={item.id}
            item={item}
            nested
            columns={columns}
            onOpenDetails={() => void handleOpenProductDetails(item)}
          />
        ))}
    </React.Fragment>
  );

  return (
    <div className="min-h-full w-full bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-[1640px] px-4 pt-[26px] pb-10 sm:px-6 lg:px-7">
        {/* Page Header */}
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-black/10 pb-[16px]">
          <div>
            <h1 className="text-[22px] font-normal leading-tight text-black">
              Category
            </h1>
            <p className="mt-[4px] text-[12px] font-normal text-[#6B7280]">
              {liveMode
                ? `${products.length} ${products.length === 1 ? "product" : "products"} · times are in UTC+7`
                : emptyText}
            </p>
          </div>

          {liveMode && (
            <ExportCsvButton
              kind="cv-output"
              label="Export CV Output"
              request={(kind, range) => createApiClient(getIdToken).exportCsvLink(kind, range)}
              className="flex h-[36px] items-center gap-[8px] rounded-[8px] border border-[#E5E7EB] bg-white pl-[14px] pr-[16px] text-[13px] font-medium text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
            />
          )}
        </header>

        {/* Toolbar */}
        <section
          aria-label="Product toolbar"
          className="mt-[16px] flex flex-wrap items-center justify-end gap-2.5"
        >
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
                placeholder={canReview ? "Search name, SKU code or barcode" : "Search by name"}
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

            {showStoreFilter(storeCount) && (
              <ToolbarDropdown
                label="Store:"
                value={storeFilter}
                options={storeDropdownOptions}
                onChange={setStoreFilter}
              />
            )}
            <ToolbarDropdown
              label="Category:"
              value={categoryFilter}
              options={categoryDropdownOptions}
              onChange={setCategoryFilter}
            />
            {canReview && (
              <ToolbarDropdown
                label="Status:"
                value={statusFilter}
                options={STATUS_FILTER_OPTIONS}
                onChange={setStatusFilter}
              />
            )}
            <ToolbarDropdown
              label="Sort:"
              value={sortBy}
              options={sortOptions(canReview)}
              onChange={setSortBy}
            />
          </div>
        </section>

        {/* Cameras that cannot see the display: the numbers below are from the last check that did (live only) */}
        {displayLine && (
          <p
            data-display-banner
            role="status"
            className="mt-[12px] whitespace-pre-line rounded-[10px] border border-[#FDE68A] bg-[#FFFBEB] px-[14px] py-[10px] text-[12.5px] leading-[1.45] text-[#92400E]"
          >
            {displayLine}
          </p>
        )}

        {/* Review queue: doubtful readings waiting for a person (the team only) */}
        {canReview && liveQueue !== null && (
          <ReviewBanner
            items={liveQueue}
            unrecognizedUnits={unrecognizedCount}
            onOpen={() => setReviewQueueOpen(true)}
          />
        )}

        {/* SKU Table (Horizontal scroll wrapper for narrow viewports) */}
        <section aria-label="SKU product list" className="mt-[16px] overflow-x-auto pb-2">
          <div style={{ minWidth: tableMinWidth }}>
            {/* Table Header */}
            <div className="flex h-[32px] items-center px-[16px] text-[11px] font-semibold tracking-[0.036em] text-[#6B7280] uppercase">
              <div className="flex flex-[2.4] min-w-[240px] items-center gap-[10px] pr-[12px]">
                <span>PRODUCT</span>
                {groups.length > 0 && (
                  <button
                    type="button"
                    onClick={toggleAllGroups}
                    className="rounded-[5px] px-[6px] py-[2px] text-[11px] font-medium normal-case tracking-normal text-[#0051C3] hover:bg-[#EEF4FF] cursor-pointer"
                  >
                    {allGroupsExpanded ? "Collapse all" : "Expand all"}
                  </button>
                )}
              </div>
              <div className="w-[126px] shrink-0 pr-[12px]">CATEGORY</div>
              <div className="w-[82px] shrink-0 pr-[12px]">PACK</div>
              {columns.skuCode && <div className="w-[152px] shrink-0 pr-[12px]">SKU CODE</div>}
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
              {columns.confidence && (
                <div className="w-[140px] shrink-0 pr-[12px]">
                  <button
                    type="button"
                    onClick={() => setSortBy("Confidence (high → low)")}
                    className="uppercase hover:text-[#111827] transition-colors cursor-pointer"
                  >
                    CONFIDENCE
                  </button>
                </div>
              )}
              {columns.stores && <div className="w-[128px] shrink-0 pr-[12px]">AVAIL IN STORES</div>}
              <div className="w-[64px] shrink-0 text-right">ACTIONS</div>
            </div>

            {/* Table Rows */}
            <div className="mt-[8px] flex flex-col gap-[8px]">
              {filteredProducts.length === 0 ? (
                <div className="flex h-[140px] items-center justify-center rounded-[10px] border border-[#EFF0F6] bg-white text-[13px] text-[#6B7280]">
                  {emptyText}
                </div>
              ) : (
                <>
                  {mainGroups.map(renderGroup)}
                  {offPlanGroups.length > 0 && (
                    <button
                      type="button"
                      data-off-plan
                      aria-expanded={showOffPlan}
                      onClick={() => setOffPlanOpen((open) => !open)}
                      className="flex h-[40px] items-center gap-[8px] rounded-[10px] border border-dashed border-[#D1D5DB] bg-[#F9FAFB] px-[16px] text-left text-[12.5px] font-medium text-[#374151] transition-colors hover:border-[#9CA3AF] cursor-pointer"
                    >
                      <ChevronDown
                        className={`h-[14px] w-[14px] shrink-0 text-[#6B7280] transition-transform ${showOffPlan ? "" : "-rotate-90"}`}
                        strokeWidth={2}
                      />
                      <span>
                        Not on this store&apos;s shelf plan ({offPlan.length})
                      </span>
                    </button>
                  )}
                  {showOffPlan && offPlanGroups.map(renderGroup)}
                </>
              )}
            </div>
          </div>
        </section>
      </div>

      {/* Product Details / Validation Card Modal (aligned with CV Output 16-col spec) */}
      <ProductDetailsModal
        key={viewingProduct ? `${viewingProduct.id}|${viewingProduct.reviewQueueKey ?? ""}` : "closed"}
        product={viewingProduct}
        canReview={canReview}
        onClose={closeCard}
        onSaveAudit={handleSaveAudit}
        onConfirm={liveMode && viewingProduct?.reviewQueueKey ? confirmCard : undefined}
        onRefreshDetail={() =>
          !viewingProduct
            ? Promise.resolve(null)
            : viewingProduct.reviewQueueKey
              ? refreshQueueCard(viewingProduct.reviewQueueKey)
              : loadProductDetail(viewingProduct)
        }
      />

      {/* Review queue: readings the model was unsure about (opened from the banner, live only) */}
      {canReview && reviewQueueOpen && liveQueue && (
        <ReviewQueueDialog
          items={liveQueue}
          onClose={() => setReviewQueueOpen(false)}
          onConfirm={(det) => void confirmQueueItem(det)}
          onCorrect={openQueueCorrection}
        />
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
