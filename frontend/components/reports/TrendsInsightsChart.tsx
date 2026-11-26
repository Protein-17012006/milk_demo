"use client";

import React, { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Box, CircleDollarSign, Repeat } from "lucide-react";
import type { ApiTrendPoint } from "@/lib/api";
import { trendRows } from "@/lib/trend-rows";

// The model's accuracy by day is a number for the team: it is on the Model page ("By day"), not here.
export type TrendTab = "total_stock" | "oos" | "restock_volume";

const METRIC_TABS: {
  key: TrendTab;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  explain: string;
  unit?: string;
}[] = [
  {
    key: "total_stock",
    label: "Total Stock Units",
    icon: Box,
    explain: "Average units of the store's expected SKUs on the shelf per check, opening hours only.",
  },
  {
    key: "oos",
    label: "Out-of-Stock (OOS)",
    icon: CircleDollarSign,
    explain: "Times an expected SKU ran out: 0 units for two checks in a row (10 minutes).",
  },
  {
    key: "restock_volume",
    label: "Restock Volume",
    icon: Repeat,
    explain: "Units put back on the shelf: rises of 2 or more that held for two checks in a row.",
  },
];

interface TrendsInsightsChartProps {
  /** Points per tab from GET /reports/trends; null while signed out or loading. */
  trends: Record<TrendTab, ApiTrendPoint[] | null>;
  /** Why the shelf tabs have no numbers (for example, no opening hours yet); null when they can have numbers. */
  blockedText: string | null;
}

export function TrendsInsightsChart({ trends, blockedText }: TrendsInsightsChartProps) {
  const [active, setActive] = useState<TrendTab>("total_stock");
  const tab = METRIC_TABS.find((t) => t.key === active) ?? METRIC_TABS[0];
  const points = trends[active];
  const rows = trendRows(points ?? [], tab.unit);
  const hasData = rows.some((r) => r.value !== null);
  const emptyText =
    points === null
      ? "Trends appear once your account is approved."
      : (blockedText ?? "Nothing counted in this period yet.");

  return (
    <div className="flex h-[440px] flex-col rounded-[18px] border border-[#EFF0F6] bg-white px-[24px] pt-[22px] pb-[18px]">
      <h2 className="text-[16px] font-medium text-black">Trends &amp; Insights</h2>

      <div className="mt-[18px] inline-flex w-fit max-w-full flex-wrap items-center gap-[3px] rounded-full bg-[#F7F7F7] p-[4px]">
        {METRIC_TABS.map((t) => {
          const Icon = t.icon;
          const isActive = active === t.key;
          return (
            <button
              key={t.key}
              type="button"
              aria-pressed={isActive}
              onClick={() => setActive(t.key)}
              className={`flex items-center gap-[5px] rounded-full px-[10px] py-[5px] text-[10.5px] transition-all cursor-pointer ${
                isActive
                  ? "bg-white font-medium text-black shadow-[0_1px_3px_rgba(0,0,0,0.06)]"
                  : "bg-transparent font-normal text-[#868686] hover:text-black/80"
              }`}
            >
              <Icon className="h-[12px] w-[12px] shrink-0" strokeWidth={1.7} />
              <span className="whitespace-nowrap">{t.label}</span>
            </button>
          );
        })}
      </div>

      <p data-trend-explainer className="mt-[10px] max-w-[78ch] text-[12px] leading-[1.5] text-[#6B7280]">
        {tab.explain}
      </p>

      {hasData ? (
        <div className="mt-[12px] min-h-0 w-full flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#EFF0F6" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={20} />
              <YAxis tick={{ fontSize: 11 }} unit={tab.unit} width={44} domain={tab.unit === "%" ? [0, 100] : [0, "auto"]} />
              <Tooltip formatter={(v) => (typeof v === "number" ? `${v}${tab.unit ?? ""}` : "—")} />
              <Line
                type="monotone"
                dataKey="value"
                name={tab.label}
                stroke="#EE730A"
                strokeWidth={2}
                dot={{ r: 2 }}
                isAnimationActive={false}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="mt-[12px] flex min-h-0 w-full flex-1 items-center justify-center rounded-[12px] border border-dashed border-[#E5E7EB] px-6 text-center">
          <p className="max-w-[360px] text-[12.5px] leading-[1.5] text-[#9CA3AF]">{emptyText}</p>
        </div>
      )}
    </div>
  );
}
