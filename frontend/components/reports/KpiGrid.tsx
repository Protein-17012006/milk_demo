"use client";

import React from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import type { ApiKpiResponse, ApiTrendPoint } from "@/lib/api";
import { namesText, type ShelfNowSummary } from "@/lib/shelf-now";
import { blockedText, coverageText, ptsChange, restockDefinition } from "@/lib/shelf-ui";

// Shown wherever there is no value; the cards never show a number the backend did not return.
const NO_VALUE = "—";
const CARD = "flex min-h-[150px] flex-col rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[16px] pb-[14px]";
const NO_PLAN = "No shelf plan yet. An administrator sets it in Settings.";

interface KpiGridProps {
  /** Totals of the "On the shelf now" table; null until the product list has come back (or when it failed). */
  summary: ShelfNowSummary | null;
  /** Names of the plan's products that are out of stock now, in the table's order. */
  outNames: string[];
  kpi: ApiKpiResponse | null;
  sparklines: { osa: ApiTrendPoint[] | null; restock: ApiTrendPoint[] | null };
  days: number;
  storeName?: string;
}

function OrangeSparkline({ points, gradientId, scale = 1 }: { points: ApiTrendPoint[] | null; gradientId: string; scale?: number }) {
  const data = (points ?? []).filter((p) => p.value !== null).map((p, idx) => ({ idx, value: (p.value as number) * scale }));
  if (data.length < 2) return <div className="h-[36px] w-full" aria-hidden="true" />;
  return (
    <div className="mt-auto h-[36px] w-full overflow-hidden">
      <ResponsiveContainer width="100%" height="100%" debounce={180}>
        <AreaChart data={data} margin={{ top: 4, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#EE730A" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#EE730A" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <Area type="monotone" dataKey="value" stroke="#EE730A" strokeWidth={1.75} fill={`url(#${gradientId})`} isAnimationActive={false} dot={false} activeDot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function Title({ children }: { children: React.ReactNode }) {
  return <p className="text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">{children}</p>;
}

function Value({ children, unit, tone }: { children: React.ReactNode; unit?: string; tone?: "alert" }) {
  return (
    <p className="mt-[8px] flex items-baseline gap-[5px]">
      <span data-kpi-value className={`text-[24px] font-bold leading-none ${tone === "alert" ? "text-[#DC2626]" : "text-black"}`}>
        {children}
      </span>
      {unit && <span className="text-[12.5px] font-medium text-[#6B7280]">{unit}</span>}
    </p>
  );
}

/** One line under the number: what it covers, the change, or the reason it is missing. */
function Sub({ children, data }: { children: React.ReactNode; data?: string }) {
  return (
    <p data-kpi-sub={data} className="mt-[6px] text-[11.5px] leading-[1.4] text-[#374151]">
      {children}
    </p>
  );
}

/** Four numbers a viewer can read at a glance: what is on the shelf, what ran out, how often there was stock, and
 * how fast the store restocks. The model's own numbers (processing time, accuracy) live on the Model page. */
export function KpiGrid({ summary, outNames, kpi, sparklines, days, storeName }: KpiGridProps) {
  const period = days === 1 ? "yesterday" : `the previous ${days} days`;
  const osa = kpi?.osa;
  const restock = kpi?.restock_rate;
  const osaDelta = osa ? ptsChange(osa.value, osa.previous) : null;
  const osaPercent = osa?.value == null ? null : Math.round(osa.value * 1000) / 10;
  const hasPlan = summary !== null && summary.products > 0;
  const noPlan = summary !== null && summary.products === 0;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div data-kpi="on-shelf" className={CARD}>
        <Title>On the shelf now</Title>
        <Value unit={hasPlan ? (summary.units === 1 ? "unit" : "units") : undefined}>
          {hasPlan ? summary.units.toLocaleString("en-US") : NO_VALUE}
        </Value>
        {hasPlan && (
          <Sub data="on-shelf">
            {summary.products} {summary.products === 1 ? "product" : "products"} on the shelf plan
          </Sub>
        )}
        {noPlan && <Sub data="on-shelf">{NO_PLAN}</Sub>}
      </div>

      <div data-kpi="oos-now" className={CARD}>
        <Title>Out of stock now</Title>
        <Value tone={hasPlan && summary.out > 0 ? "alert" : undefined} unit={hasPlan ? (summary.out === 1 ? "product" : "products") : undefined}>
          {hasPlan ? summary.out : NO_VALUE}
        </Value>
        {hasPlan && <Sub data="oos-now">{summary.out > 0 ? namesText(outNames) : "Every product on the plan has stock."}</Sub>}
        {hasPlan && summary.low > 0 && <Sub data="low-now">Low: {summary.low}</Sub>}
        {noPlan && <Sub data="oos-now">{NO_PLAN}</Sub>}
      </div>

      <div
        data-kpi="osa"
        className={CARD}
        title={[
          "Checks in opening hours where an expected SKU had at least 1 unit.",
          kpi?.coverage ? coverageText(kpi.coverage) : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <Title>On-Shelf Availability</Title>
        <Value>{osaPercent === null ? NO_VALUE : `${osaPercent}%`}</Value>
        <Sub data="osa">
          {osa?.blocked_reason
            ? blockedText(osa.blocked_reason, storeName)
            : osaDelta
              ? `${osaDelta} vs ${period}`
              : "Share of opening-hours checks where a product had stock."}
        </Sub>
        <OrangeSparkline points={sparklines.osa} gradientId="kpiOsaSparkline" scale={100} />
      </div>

      <div data-kpi="restock" className={CARD} title={restockDefinition(days, restock?.measured_days)}>
        <Title>Restock rate</Title>
        <Value unit={restock?.units_per_day != null ? "units/day" : undefined}>{restock?.units_per_day ?? NO_VALUE}</Value>
        <Sub data="restock">
          {restock?.units_per_day == null
            ? restock?.blocked_reason
              ? blockedText(restock.blocked_reason, storeName)
              : NO_VALUE
            : restock.previous_units_per_day != null
              ? `vs ${restock.previous_units_per_day} units/day before`
              : "No earlier period to compare"}
        </Sub>
        <OrangeSparkline points={sparklines.restock} gradientId="kpiRestockSparkline" />
      </div>
    </div>
  );
}
