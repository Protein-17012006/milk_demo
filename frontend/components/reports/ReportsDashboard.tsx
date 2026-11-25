"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { useAuth } from "@/lib/auth";
import {
  createApiClient,
  type ApiKpiResponse,
  type ApiReportsSeriesPoint,
  type ApiReportsSeriesResponse,
  type ApiStore,
  type ApiTrendPoint,
  type ApiTrendsResponse,
  type TrendMetric,
} from "@/lib/api";
import { FilterBar } from "./FilterBar";
import { KpiGrid } from "./KpiGrid";
import { MonthlyStockChart } from "./MonthlyStockChart";
import { TrendsInsightsChart } from "./TrendsInsightsChart";
import { RecentActivitiesCard, type ActivityKind } from "./RecentActivitiesCard";
import {
  ALL_STORES_LABEL,
  DEFAULT_TIMEFRAME,
  categoryParam,
  daysOf,
  kpisFromApi,
  storeParam,
  type CategoryOption,
  type TimeframeOption,
} from "@/lib/reports-ui";
import { alertAccuracyByTypeText, alertAccuracyText, blockedText } from "@/lib/shelf-ui";

const TREND_METRICS: TrendMetric[] = ["total_stock", "oos", "accuracy", "restock_volume", "osa"];
type Trends = Record<TrendMetric, ApiTrendPoint[] | null>;
const NO_TRENDS: Trends = { total_stock: null, oos: null, accuracy: null, restock_volume: null, osa: null };

/** The Dashboard: every card and chart follows the Timeframe, Store and Category filters (spec 2026-11-24). */
export function ReportsDashboard() {
  const { isApproved, getIdToken, user } = useAuth();
  const [timeframe, setTimeframe] = useState<TimeframeOption>(DEFAULT_TIMEFRAME);
  const [store, setStore] = useState<string>(ALL_STORES_LABEL);
  const [category, setCategory] = useState<CategoryOption>("All Categories");
  const [liveKpi, setLiveKpi] = useState<ApiKpiResponse | null>(null);
  const [liveStores, setLiveStores] = useState<ApiStore[] | null>(null);
  const [liveSeries, setLiveSeries] = useState<ApiReportsSeriesPoint[] | null>(null);
  const [liveTrends, setLiveTrends] = useState<Trends>(NO_TRENDS);

  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);
  const days = daysOf(timeframe);
  const storeId = storeParam(store);
  const categoryValue = categoryParam(category);
  const query = useMemo(() => ({ days, storeId, category: categoryValue }), [days, storeId, categoryValue]);

  useEffect(() => {
    if (!isApproved) return;
    let cancelled = false;
    api
      .getStores()
      .then((res) => {
        if (!cancelled) setLiveStores(res.items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [isApproved, api]);

  useEffect(() => {
    if (!isApproved) return;
    let cancelled = false;
    // Each part shows what it got: one failed call leaves only its own card at "—", never the previous filter's
    // numbers under the new filter labels.
    Promise.allSettled([
      api.getKpi(query),
      api.getReportsSeries({ storeId: query.storeId, category: query.category }),
      ...TREND_METRICS.map((metric) => api.getTrends(metric, query)),
    ]).then(([kpiRes, seriesRes, ...trendRes]) => {
      if (cancelled) return;
      setLiveKpi(kpiRes.status === "fulfilled" ? (kpiRes.value as ApiKpiResponse) : null);
      setLiveSeries(seriesRes.status === "fulfilled" ? (seriesRes.value as ApiReportsSeriesResponse).series : null);
      setLiveTrends(
        Object.fromEntries(
          TREND_METRICS.map((m, i) => {
            const r = trendRes[i];
            return [m, r.status === "fulfilled" ? (r.value as ApiTrendsResponse).points : null];
          })
        ) as Trends
      );
    });
    return () => {
      cancelled = true;
    };
  }, [isApproved, api, query]);

  // Signed out, nothing from the API is shown.
  const kpi = isApproved ? liveKpi : null;
  const stores = isApproved ? liveStores : null;
  const series = isApproved ? liveSeries : null;
  const trends = isApproved ? liveTrends : NO_TRENDS;

  const storeOptions = useMemo(() => {
    if (!stores) return undefined;
    return [`${ALL_STORES_LABEL} (${stores.length})`, ...stores.map((s) => `${s.store_id} — ${s.store_name}`)];
  }, [stores]);
  const storeName = storeId ?? (stores && stores.length === 1 ? stores[0].store_id : undefined);
  const kpis = useMemo(() => kpisFromApi(kpi), [kpi]);
  const shelfBlocked = kpi?.osa?.blocked_reason === "no_hours" ? blockedText("no_hours", storeName) : null;

  const canVerify = (user?.groups ?? []).some((g) => g === "team_admin" || g === "field_team");
  const loadEvents = useCallback(
    (kind: ActivityKind, cursor?: string) => api.getShelfEvents({ ...query, kind, limit: 20, cursor }),
    [api, query]
  );

  const handleDownloadCsv = async () => {
    if (isApproved) {
      try {
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
        // fall through to the summary export
      }
    }
    const show = (v: number | string | null, suffix = "") => (v === null ? "—" : `${v}${suffix}`);
    const rows = [
      ["Metric", "Value"],
      ["Timeframe", timeframe],
      ["Store", store],
      ["Category", category],
      ["Active Stores Monitored", kpis.activeStores === null ? "—" : `${kpis.activeStores}/${kpis.totalStores ?? "—"}`],
      ["Total On-Shelf Units (now)", show(kpis.totalOnShelfUnits)],
      ["Avg. Inference Time", show(kpis.avgInferenceTime)],
      ["On-Shelf Availability (OSA)", show(kpis.osaPercent, "%")],
      ["Top 50 SKU Accuracy", show(kpis.top50SkuAccuracy, "%")],
      ["Restock Rate (vs Last Cycle)", show(kpis.restockRateDelta)],
    ];
    const csv = rows.map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `reports-${days}-days.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto w-full px-4 pt-6 pb-8 sm:px-6 lg:px-7">
      <header className="flex items-center justify-between border-b border-black/10 pb-[18px]">
        <div>
          <h1 className="text-[22px] font-normal leading-tight text-black">Reports</h1>
          {kpi && (
            <p className="mt-1 text-[12px] text-[#6B7280]">
              Live AWS data, {kpi.captures_count} captures synced. Shelf numbers are worked out every 5 minutes from
              the store&apos;s checks in opening hours.
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

      <section aria-label="Report filters" className="mt-[16px]">
        <FilterBar
          timeframe={timeframe}
          store={store}
          category={category}
          storeOptions={storeOptions}
          onTimeframeChange={setTimeframe}
          onStoreChange={setStore}
          onCategoryChange={setCategory}
        />
      </section>

      <section aria-label="Key metrics and stock count" className="mt-[28px] grid grid-cols-1 gap-[22px] xl:grid-cols-12">
        <div className="xl:col-span-6">
          <KpiGrid
            metrics={kpis}
            kpi={kpi}
            sparklines={{ osa: trends.osa, restock: trends.restock_volume }}
            days={days}
            storeName={storeName}
          />
        </div>
        <div className="xl:col-span-6">
          <MonthlyStockChart series={series} />
        </div>
      </section>

      <section aria-label="Trends and recent shelf activities" className="mt-[22px] grid grid-cols-1 gap-[22px] xl:grid-cols-12">
        <div className="xl:col-span-8">
          <TrendsInsightsChart
            trends={{
              total_stock: trends.total_stock,
              oos: trends.oos,
              accuracy: trends.accuracy,
              restock_volume: trends.restock_volume,
            }}
            blockedText={shelfBlocked}
          />
        </div>
        <div className="xl:col-span-4">
          <RecentActivitiesCard
            load={isApproved ? loadEvents : null}
            reloadKey={`${days}|${storeId ?? ""}|${categoryValue ?? ""}`}
            blockedText={shelfBlocked}
            accuracyLine={alertAccuracyText(kpi?.alert_accuracy, canVerify)}
            accuracyByType={alertAccuracyByTypeText(kpi?.alert_accuracy?.by_type)}
            canVerify={canVerify}
            loadPhotos={isApproved ? api.getShelfEventPhotos : null}
            saveVerdict={isApproved ? api.saveShelfEventVerdict : null}
          />
        </div>
      </section>
    </div>
  );
}
