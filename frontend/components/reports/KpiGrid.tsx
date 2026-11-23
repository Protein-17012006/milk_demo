"use client";

import React from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import type { ApiKpiResponse, ApiTrendPoint } from "@/lib/api";
import type { KpiMetrics } from "@/lib/reports-ui";
import { blockedText, ptsChange } from "@/lib/shelf-ui";

// Shown wherever the API has no value; the cards never show a number the backend did not return.
const NO_VALUE = "—";
const percent = (v: number | null) => (v === null ? NO_VALUE : `${v}%`);
const CARD = "flex min-h-[170px] flex-col rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[18px] pb-[14px]";

interface KpiGridProps {
  metrics: KpiMetrics;
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
  return <p className="min-h-[34px] text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">{children}</p>;
}

function Value({ children }: { children: React.ReactNode }) {
  return <span className="text-[22px] font-bold leading-none text-black">{children}</span>;
}

/** One line under the number: the change or the reason it is missing. */
function Sub({ children, data }: { children: React.ReactNode; data?: string }) {
  return (
    <p data-kpi-sub={data} className="mt-[6px] text-[11.5px] leading-[1.35] text-[#374151]">
      {children}
    </p>
  );
}

/** What the card measures, from the spec's definitions. */
function Defn({ children }: { children: React.ReactNode }) {
  return <p className="mt-[4px] text-[11px] leading-[1.35] text-[#9CA3AF]">{children}</p>;
}

export function KpiGrid({ metrics, kpi, sparklines, days, storeName }: KpiGridProps) {
  const period = days === 1 ? "yesterday" : `the previous ${days} days`;
  const osa = kpi?.osa;
  const top = kpi?.top_50_sku_accuracy;
  const restock = kpi?.restock_rate;
  const osaDelta = osa ? ptsChange(osa.value, osa.previous) : null;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className={CARD}>
        <Title>Active Stores Monitored</Title>
        <div className="mt-[10px] flex items-baseline">
          <Value>{metrics.activeStores ?? NO_VALUE}</Value>
          {metrics.activeStores !== null && metrics.totalStores !== null && (
            <span className="text-[15.5px] font-semibold leading-none text-black/50">/{metrics.totalStores}</span>
          )}
        </div>
        <Defn>Stores whose camera sent captures.</Defn>
      </div>

      <div className={CARD}>
        <Title>Total On-Shelf Units (now)</Title>
        <div className="mt-[10px]">
          <Value>{metrics.totalOnShelfUnits === null ? NO_VALUE : metrics.totalOnShelfUnits.toLocaleString("en-US")}</Value>
        </div>
        <Defn>Units counted on the shelves at the latest capture.</Defn>
      </div>

      <div className={CARD}>
        <Title>Avg. Inference Time</Title>
        <div className="mt-[10px]">
          <Value>{metrics.avgInferenceTime ?? NO_VALUE}</Value>
        </div>
        <Defn>Model time per image; Datagent&apos;s limit is 30 s.</Defn>
      </div>

      <div data-kpi="osa" className={CARD}>
        <Title>On-Shelf Availability (OSA)</Title>
        <Value>{percent(metrics.osaPercent)}</Value>
        <Sub data="osa">
          {osa?.blocked_reason ? blockedText(osa.blocked_reason, storeName) : osaDelta ? `${osaDelta} vs ${period}` : "No previous period to compare"}
        </Sub>
        <Defn>Checks in opening hours where an expected SKU had at least 1 unit.</Defn>
        <OrangeSparkline points={sparklines.osa} gradientId="kpiOsaSparkline" scale={100} />
      </div>

      <div data-kpi="top50" className={CARD}>
        <Title>Top 50 SKU Accuracy</Title>
        <Value>{percent(metrics.top50SkuAccuracy)}</Value>
        <Sub data="top50">
          {top?.blocked_reason
            ? blockedText(top.blocked_reason, storeName)
            : top
              ? `From ${top.n_frames} ${top.n_frames === 1 ? "frame" : "frames"} the team labelled`
              : NO_VALUE}
        </Sub>
        <Defn>{top?.scope_note ?? "Boxes named with the right SKU."}</Defn>
      </div>

      <div data-kpi="restock" className={CARD}>
        <Title>Restock Rate (vs Last Cycle)</Title>
        <Value>{metrics.restockRateDelta ?? NO_VALUE}</Value>
        <Sub data="restock">
          {restock && restock.units_per_day !== null
            ? `${restock.units_per_day} units/day vs ${restock.previous_units_per_day ?? NO_VALUE}`
            : restock?.blocked_reason
              ? blockedText(restock.blocked_reason, storeName)
              : NO_VALUE}
        </Sub>
        <Defn>Units restocked per day against {period}.</Defn>
        <OrangeSparkline points={sparklines.restock} gradientId="kpiRestockSparkline" />
      </div>
    </div>
  );
}
