"use client";

import React, { useState } from "react";
import { Box, CircleDollarSign, Filter, Repeat } from "lucide-react";
import type { TrendMetricKey } from "@/lib/reports-ui";

const METRIC_TABS: {
  key: TrendMetricKey;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}[] = [
  { key: "totalStock", label: "Total Stock Units", icon: Box },
  { key: "oos", label: "Out-of-Stock (OOS)", icon: CircleDollarSign },
  { key: "accuracy", label: "Detection Accuracy", icon: Filter },
  { key: "restockVolume", label: "Restock Volume", icon: Repeat },
];

// The backend keeps no weekly history for these metrics yet, so every tab shows an empty state
// instead of a drawn line. Wire a series here once the API serves one.
export function TrendsInsightsChart() {
  const [activeMetric, setActiveMetric] =
    useState<TrendMetricKey>("totalStock");
  const activeLabel =
    METRIC_TABS.find((tab) => tab.key === activeMetric)?.label ?? "";

  return (
    <div className="flex h-[440px] flex-col rounded-[18px] border border-[#EFF0F6] bg-white px-[24px] pt-[22px] pb-[18px]">
      {/* Header Row */}
      <div className="flex items-center justify-between">
        <h2 className="text-[16px] font-medium text-black">
          Trends &amp; Insights
        </h2>
      </div>

      {/* Segmented Tabs Pill Bar */}
      <div className="mt-[18px] inline-flex w-fit max-w-full flex-wrap items-center gap-[3px] rounded-full bg-[#F7F7F7] p-[4px]">
        {METRIC_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeMetric === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveMetric(tab.key)}
              className={`flex items-center gap-[5px] rounded-full px-[10px] py-[5px] text-[10.5px] transition-all cursor-pointer ${
                isActive
                  ? "bg-white font-medium text-black shadow-[0_1px_3px_rgba(0,0,0,0.06)]"
                  : "bg-transparent font-normal text-[#868686] hover:text-black/80"
              }`}
            >
              <Icon className="h-[12px] w-[12px] shrink-0" strokeWidth={1.7} />
              <span className="whitespace-nowrap">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Empty state until the API serves a history for the selected metric */}
      <div className="mt-[22px] flex flex-1 min-h-0 w-full items-center justify-center rounded-[12px] border border-dashed border-[#E5E7EB] px-6 text-center">
        <p className="max-w-[360px] text-[12.5px] leading-[1.5] text-[#9CA3AF]">
          No {activeLabel} trend yet: the API does not serve this series. The
          Shelf Stock Count chart shows the stock history that exists.
        </p>
      </div>
    </div>
  );
}
