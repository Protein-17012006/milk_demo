"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
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
import { ExportCsvButton } from "@/components/common/ExportCsvButton";
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
import { alertAccuracyByTypeText, alertAccuracyText, blockedText, displayBanner } from "@/lib/shelf-ui";
import { showStoreFilter } from "@/lib/products-ui";

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

  const displayLine = displayBanner(kpi?.displays ?? []);

  return (
    <div className="mx-auto w-full px-4 pt-6 pb-8 sm:px-6 lg:px-7">
      <header className="flex items-center justify-between border-b border-black/10 pb-[18px]">
        <div>
          <h1 className="text-[22px] font-normal leading-tight text-black">Dashboard</h1>
          {kpi && (
            <p className="mt-1 text-[12px] text-[#6B7280]">
              Shelf numbers are worked out every 5 minutes from the store&apos;s checks in opening hours.
            </p>
          )}
        </div>
        {isApproved && (
          <ExportCsvButton
            kind="capture-log"
            label="Download capture log"
            request={api.exportCsvLink}
            className="inline-flex items-center gap-[6px] whitespace-nowrap rounded-[8px] px-2.5 py-1.5 text-[13px] font-semibold text-[#4D4D4D] hover:bg-black/[0.04] hover:text-black transition-colors cursor-pointer"
          />
        )}
      </header>

      <section aria-label="Report filters" className="mt-[16px]">
        <FilterBar
          timeframe={timeframe}
          store={store}
          category={category}
          storeOptions={storeOptions}
          showStore={showStoreFilter(stores?.length ?? 0)}
          onTimeframeChange={setTimeframe}
          onStoreChange={setStore}
          onCategoryChange={setCategory}
        />
      </section>

      {/* Cameras that cannot see the display: "now" on this page is the last check that did */}
      {displayLine && (
        <p
          data-display-banner
          role="status"
          className="mt-[12px] whitespace-pre-line rounded-[10px] border border-[#FDE68A] bg-[#FFFBEB] px-[14px] py-[10px] text-[12.5px] leading-[1.45] text-[#92400E]"
        >
          {displayLine}
        </p>
      )}

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
