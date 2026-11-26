"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  createApiClient,
  type ApiKpiResponse,
  type ApiProductsResponse,
  type ApiStore,
  type ApiTrendPoint,
  type ApiTrendsResponse,
  type TrendMetric,
} from "@/lib/api";
import { ExportCsvButton } from "@/components/common/ExportCsvButton";
import { FilterBar } from "./FilterBar";
import { KpiGrid } from "./KpiGrid";
import { ShelfNowTable } from "./ShelfNowTable";
import { TrendsInsightsChart } from "./TrendsInsightsChart";
import { RecentActivitiesCard, type ActivityKind } from "./RecentActivitiesCard";
import {
  ALL_STORES_LABEL,
  DEFAULT_TIMEFRAME,
  categoryParam,
  daysOf,
  storeParam,
  type CategoryOption,
  type TimeframeOption,
} from "@/lib/reports-ui";
import { alertAccuracyByTypeText, alertAccuracyText, blockedText, displayBanner } from "@/lib/shelf-ui";
import { showStoreFilter } from "@/lib/products-ui";
import { shelfNowRows, shelfNowSummary, updatedText } from "@/lib/shelf-now";

const TREND_METRICS: TrendMetric[] = ["total_stock", "oos", "accuracy", "restock_volume", "osa"];
type Trends = Record<TrendMetric, ApiTrendPoint[] | null>;
const NO_TRENDS: Trends = { total_stock: null, oos: null, accuracy: null, restock_volume: null, osa: null };

/** The product list as the Dashboard holds it: the answer, when it was read, and the line that says how fresh the
 * numbers are (worked out when the answer arrives, so drawing the page never reads the clock). */
interface LoadedProducts {
  data: ApiProductsResponse;
  loadedAt: number;
  updated: string | null;
}

/**
 * The Dashboard. On top, what a viewer opens it for: each product of the shelf plan with its units now, and what
 * ran out. Below, how the shelf did over the chosen Timeframe (spec 2026-11-24). The table shows the latest
 * reading, the same numbers as the Category page; the cards and charts under it follow all the filters.
 */
export function ReportsDashboard() {
  const { isApproved, getIdToken, user } = useAuth();
  const [timeframe, setTimeframe] = useState<TimeframeOption>(DEFAULT_TIMEFRAME);
  const [store, setStore] = useState<string>(ALL_STORES_LABEL);
  const [category, setCategory] = useState<CategoryOption>("All Categories");
  const [liveKpi, setLiveKpi] = useState<ApiKpiResponse | null>(null);
  const [liveStores, setLiveStores] = useState<ApiStore[] | null>(null);
  const [liveProducts, setLiveProducts] = useState<LoadedProducts | null>(null);
  const [productsFailed, setProductsFailed] = useState(false);
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
      api.getProducts({ category: query.category }),
      ...TREND_METRICS.map((metric) => api.getTrends(metric, query)),
    ]).then(([kpiRes, productsRes, ...trendRes]) => {
      if (cancelled) return;
      setLiveKpi(kpiRes.status === "fulfilled" ? (kpiRes.value as ApiKpiResponse) : null);
      if (productsRes.status === "fulfilled") {
        const data = productsRes.value as ApiProductsResponse;
        const now = new Date();
        setLiveProducts({ data, loadedAt: now.getTime(), updated: updatedText(data.as_of, now) });
        setProductsFailed(false);
      } else {
        setLiveProducts(null);
        setProductsFailed(true);
      }
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
  const products = isApproved ? liveProducts : null;
  const trends = isApproved ? liveTrends : NO_TRENDS;

  const storeOptions = useMemo(() => {
    if (!stores) return undefined;
    return [`${ALL_STORES_LABEL} (${stores.length})`, ...stores.map((s) => `${s.store_id} — ${s.store_name}`)];
  }, [stores]);
  const storeName = storeId ?? (stores && stores.length === 1 ? stores[0].store_id : undefined);
  const shelfBlocked = kpi?.osa?.blocked_reason === "no_hours" ? blockedText("no_hours", storeName) : null;

  // What is on the shelf now: the plan's products at the latest reading, and their totals for the first two cards.
  const rows = useMemo(() => (products ? shelfNowRows(products.data.items) : null), [products]);
  const summary = useMemo(() => (rows ? shelfNowSummary(rows) : null), [rows]);
  const outNames = useMemo(() => (rows ?? []).filter((r) => r.status === "OOS").map((r) => r.name), [rows]);

  const canVerify = (user?.groups ?? []).some((g) => g === "team_admin" || g === "field_team");
  const loadEvents = useCallback(
    (kind: ActivityKind, cursor?: string) => api.getShelfEvents({ ...query, kind, limit: 20, cursor }),
    [api, query]
  );

  const displayLine = displayBanner(kpi?.displays ?? []);

  return (
    <div className="mx-auto w-full px-4 pt-6 pb-8 sm:px-6 lg:px-7">
      {/* On a phone the button sits under the title, at the right, so its panel opens inside the screen. */}
      <header className="flex flex-col gap-[6px] border-b border-black/10 pb-[18px] sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[22px] font-normal leading-tight text-black">Dashboard</h1>
          {isApproved && (
            <p className="mt-1 text-[12px] text-[#6B7280]">
              {products?.updated && (
                <>
                  <span data-updated className="font-semibold text-[#374151]">
                    {products.updated}
                  </span>
                  {" · "}
                </>
              )}
              Shelf numbers are worked out every 5 minutes in opening hours.
            </p>
          )}
        </div>
        {isApproved && (
          <div className="self-end sm:self-auto">
            <ExportCsvButton
              kind="capture-log"
              label="Download capture log"
              request={api.exportCsvLink}
              className="inline-flex items-center gap-[6px] whitespace-nowrap rounded-[8px] px-2.5 py-1.5 text-[13px] font-semibold text-[#4D4D4D] hover:bg-black/[0.04] hover:text-black transition-colors cursor-pointer"
            />
          </div>
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

      {/* The table comes first on a narrow screen: it is what a viewer came for. */}
      <section aria-label="What is on the shelf now" className="mt-[28px] grid grid-cols-1 gap-[22px] xl:grid-cols-12">
        <div className="order-2 xl:order-1 xl:col-span-5">
          <KpiGrid
            summary={summary}
            outNames={outNames}
            kpi={kpi}
            sparklines={{ osa: trends.osa, restock: trends.restock_volume }}
            days={days}
            storeName={storeName}
          />
        </div>
        <div className="order-1 xl:order-2 xl:col-span-7">
          <ShelfNowTable rows={isApproved ? rows : []} failed={isApproved && productsFailed} />
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
