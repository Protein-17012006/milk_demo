"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Download, X } from "lucide-react";
import { useSidebarSearch } from "@/components/layout/SidebarContext";
import { useAuth } from "@/lib/auth";
import { createApiClient, type ApiKpiResponse, type ApiStore } from "@/lib/api";
import { FilterBar } from "./FilterBar";
import { KpiGrid } from "./KpiGrid";
import { MonthlyStockChart } from "./MonthlyStockChart";
import { TrendsInsightsChart } from "./TrendsInsightsChart";
import { RecentActivitiesCard } from "./RecentActivitiesCard";
import {
  RECENT_SHELF_ACTIVITIES,
  getFilteredKpis,
  type CategoryOption,
  type StoreOption,
  type TimeframeOption,
} from "@/data/reports-mock";

interface ReportsDashboardProps {
  searchQuery?: string;
}

export function ReportsDashboard({ searchQuery }: ReportsDashboardProps) {
  const { searchQuery: sidebarSearchQuery } = useSidebarSearch();
  const { isApproved, getIdToken } = useAuth();
  const effectiveSearchQuery = searchQuery ?? sidebarSearchQuery;
  const [timeframe, setTimeframe] = useState<TimeframeOption>("All-time");
  const [store, setStore] = useState<string>("All Stores (30)");
  const [category, setCategory] = useState<CategoryOption>("All Categories");
  const [auditModalOpen, setAuditModalOpen] = useState(false);
  const [liveKpi, setLiveKpi] = useState<ApiKpiResponse | null>(null);
  const [liveStores, setLiveStores] = useState<ApiStore[] | null>(null);

  useEffect(() => {
    if (!isApproved) {
      setLiveKpi(null);
      setLiveStores(null);
      return;
    }
    let cancelled = false;
    const api = createApiClient(getIdToken);
    Promise.all([api.getKpi(), api.getStores()])
      .then(([kpiRes, storesRes]) => {
        if (cancelled) return;
        setLiveKpi(kpiRes);
        setLiveStores(storesRes.items);
        setStore(`All Stores (${storesRes.total})`);
      })
      .catch(() => {
        // fallback cleanly to sample metrics
      });
    return () => {
      cancelled = true;
    };
  }, [isApproved, getIdToken]);

  const dynamicStoreOptions = useMemo(() => {
    if (!liveStores) return undefined;
    return [
      `All Stores (${liveStores.length})`,
      ...liveStores.map((s) => `${s.store_id} — ${s.store_name}`),
    ];
  }, [liveStores]);

  const kpis = useMemo(() => {
    const base = getFilteredKpis(
      timeframe,
      (store.startsWith("All Stores") ? "All Stores (30)" : store) as StoreOption,
      category
    );
    if (!liveKpi) return base;
    return {
      ...base,
      activeStores: liveKpi.active_stores_monitored,
      totalStores: liveKpi.total_stores,
      totalOnShelfUnits: liveKpi.total_on_shelf_units,
      avgInferenceTime: `${liveKpi.avg_processing_time_ms} ms`,
      top50SkuAccuracy:
        liveKpi.top_50_sku_accuracy !== null
          ? liveKpi.top_50_sku_accuracy
          : base.top50SkuAccuracy,
    };
  }, [timeframe, store, category, liveKpi]);

  // Deterministic scale factor for hardcoded charts when filters change
  const chartScaleFactor = useMemo(() => {
    let factor = 1;
    if (timeframe === "This Quarter") factor *= 0.92;
    if (timeframe === "Last 30 Days") factor *= 0.84;
    if (timeframe === "Last 7 Days") factor *= 0.72;
    if (!store.startsWith("All Stores")) factor *= 0.82;
    if (category !== "All Categories") factor *= 0.85;
    return factor;
  }, [timeframe, store, category]);

  const filteredActivities = useMemo(() => {
    const q = effectiveSearchQuery.trim().toLowerCase();
    return RECENT_SHELF_ACTIVITIES.filter((item) => {
      if (!store.startsWith("All Stores") && item.storeDistrict !== store) {
        return false;
      }
      if (category !== "All Categories" && item.category !== category) {
        return false;
      }
      if (
        q &&
        !item.productName.toLowerCase().includes(q) &&
        !item.storeName.toLowerCase().includes(q) &&
        !item.status.toLowerCase().includes(q)
      ) {
        return false;
      }
      return true;
    });
  }, [store, category, effectiveSearchQuery]);

  const handleDownloadCsv = async () => {
    if (isApproved) {
      try {
        const api = createApiClient(getIdToken);
        const csvText = await api.exportCaptureLogCsv();
        const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "capture-log.csv";
        link.click();
        URL.revokeObjectURL(url);
        return;
      } catch {
        // fall through to summary export
      }
    }
    const rows = [
      ["Metric", "Value"],
      ["Timeframe", timeframe],
      ["Store", store],
      ["Category", category],
      ["Active Stores Monitored", `${kpis.activeStores}/${kpis.totalStores}`],
      ["Total On-Shelf Units", String(kpis.totalOnShelfUnits)],
      ["Avg. Inference Time", kpis.avgInferenceTime],
      ["On-Shelf Availability (OSA)", `${kpis.osaPercent}%`],
      ["Top 50 SKU Accuracy", `${kpis.top50SkuAccuracy}%`],
      ["Restock Rate (vs Last Cycle)", kpis.restockRateDelta],
    ];
    const csv = rows.map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `reports-${timeframe.toLowerCase().replace(/\s+/g, "-")}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto w-full px-4 pt-6 pb-8 sm:px-6 lg:px-7">
      {/* Page Header */}
      <header className="flex items-center justify-between border-b border-black/10 pb-[18px]">
        <div>
          <h1 className="text-[22px] font-normal leading-tight text-black">
            Reports
          </h1>
          {liveKpi && (
            <p className="mt-1 text-[12px] text-[#6B7280]">
              Live AWS data &middot; {liveKpi.captures_count} captures synced
              &middot; {liveKpi.top_50_scope_note}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={handleDownloadCsv}
          className="inline-flex items-center gap-[6px] rounded-[8px] px-2.5 py-1.5 text-[13px] font-semibold text-[#4D4D4D] hover:bg-black/[0.04] hover:text-black transition-colors cursor-pointer"
        >
          <Download className="h-[16px] w-[16px]" strokeWidth={2} />
          <span>Download</span>
        </button>
      </header>

      {/* Filter Bar */}
      <section aria-label="Report filters" className="mt-[16px]">
        <FilterBar
          timeframe={timeframe}
          store={store}
          category={category}
          storeOptions={dynamicStoreOptions}
          onTimeframeChange={setTimeframe}
          onStoreChange={setStore}
          onCategoryChange={setCategory}
        />
      </section>

      {/* Row 1: 6 KPI Cards (Left) + Monthly Shelf Stock Count Bar Chart (Right) */}
      <section
        aria-label="Key metrics and monthly stock count"
        className="mt-[28px] grid grid-cols-1 gap-[22px] xl:grid-cols-12"
      >
        <div className="xl:col-span-6">
          <KpiGrid metrics={kpis} />
        </div>
        <div className="xl:col-span-6">
          <MonthlyStockChart scaleFactor={chartScaleFactor} />
        </div>
      </section>

      {/* Row 2: Trends & Insights (Left) + Recent Shelf Activities (Right) */}
      <section
        aria-label="Trends and recent shelf activities"
        className="mt-[22px] grid grid-cols-1 gap-[22px] xl:grid-cols-12"
      >
        <div className="xl:col-span-8">
          <TrendsInsightsChart scaleFactor={chartScaleFactor} />
        </div>
        <div className="xl:col-span-4">
          <RecentActivitiesCard
            activities={filteredActivities}
            onOpenFullLog={() => setAuditModalOpen(true)}
          />
        </div>
      </section>

      {/* Full Audit Log Modal */}
      {auditModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
          onClick={() => setAuditModalOpen(false)}
        >
          <div
            className="flex max-h-[80vh] w-full max-w-[640px] flex-col overflow-hidden rounded-[18px] border border-[#EFF0F6] bg-white shadow-[0_12px_36px_rgba(0,0,0,0.16)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#EFF0F6] px-5 py-4">
              <div>
                <h3 className="text-[16px] font-semibold text-[#111827]">
                  Full Shelf Audit Log
                </h3>
                <p className="text-[12px] text-[#6B7280]">
                  Showing {filteredActivities.length} recorded shelf events
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAuditModalOpen(false)}
                aria-label="Close audit log"
                className="flex h-8 w-8 items-center justify-center rounded-full text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827] cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto divide-y divide-[#EFF0F6] px-5 py-2">
              {filteredActivities.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start justify-between gap-4 py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[11px] font-semibold text-[#111827]">
                        {item.status}
                      </span>
                      <span className="text-[13.5px] font-semibold text-[#111827]">
                        {item.productName}
                      </span>
                    </div>
                    <p className="mt-1 text-[12px] text-[#6B7280]">
                      {item.storeName} &bull; {item.category}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[12px] font-medium text-[#374151]">
                      {item.deltaText}
                    </p>
                    <p className="text-[11px] text-[#9CA3AF]">{item.timeAgo}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
