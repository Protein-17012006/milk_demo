"use client";

import React from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import type { KpiMetrics } from "@/lib/reports-ui";

// Shown wherever the API has no value yet; the cards never show a number the backend did not return.
const NO_VALUE = "—";
const percent = (v: number | null) => (v === null ? NO_VALUE : `${v}%`);

interface KpiGridProps {
  metrics: KpiMetrics;
}

interface SparklineProps {
  data: { idx: number; value: number }[];
  gradientId: string;
}

function OrangeSparkline({ data, gradientId }: SparklineProps) {
  if (data.length === 0) return <div className="h-[42px] w-full" aria-hidden="true" />;
  return (
    <div className="h-[42px] w-full overflow-hidden">
      <ResponsiveContainer width="100%" height="100%" debounce={180}>
        <AreaChart data={data} margin={{ top: 4, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#EE730A" stopOpacity={0.28} />
              <stop offset="100%" stopColor="#EE730A" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke="#EE730A"
            strokeWidth={1.75}
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function KpiGrid({ metrics }: KpiGridProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {/* Row 1, Card 1 */}
      <div className="flex h-[170px] flex-col justify-start rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[20px] pb-[18px]">
        <p className="text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">
          Active Stores Monitored
        </p>
        <div className="mt-[28px] flex items-baseline">
          <span className="text-[22px] font-bold leading-none text-black">
            {metrics.activeStores ?? NO_VALUE}
          </span>
          {metrics.activeStores !== null && metrics.totalStores !== null && (
            <span className="text-[15.5px] font-semibold leading-none text-black/50">
              /{metrics.totalStores}
            </span>
          )}
        </div>
      </div>

      {/* Row 1, Card 2 */}
      <div className="flex h-[170px] flex-col justify-start rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[20px] pb-[18px]">
        <p className="text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">
          Total On-Shelf Units
        </p>
        <div className="mt-[28px]">
          <span className="text-[22px] font-bold leading-none text-black">
            {metrics.totalOnShelfUnits === null
              ? NO_VALUE
              : metrics.totalOnShelfUnits.toLocaleString("en-US")}
          </span>
        </div>
      </div>

      {/* Row 1, Card 3 */}
      <div className="flex h-[170px] flex-col justify-start rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[20px] pb-[18px]">
        <p className="text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">
          Avg. Inference Time
        </p>
        <div className="mt-[28px]">
          <span className="text-[22px] font-bold leading-none text-black">
            {metrics.avgInferenceTime ?? NO_VALUE}
          </span>
        </div>
      </div>

      {/* Row 2, Card 4 */}
      <div className="flex h-[170px] flex-col justify-start rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[20px] pb-[18px]">
        <p className="min-h-[34px] text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">
          On-Shelf Availability (OSA)
        </p>
        <div className="mt-[10px]">
          <span className="text-[22px] font-bold leading-none text-black">
            {percent(metrics.osaPercent)}
          </span>
        </div>
      </div>

      {/* Row 2, Card 5 */}
      <div className="flex h-[170px] flex-col justify-between rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[20px] pb-[16px]">
        <div>
          <p className="min-h-[34px] text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">
            Top 50 SKU Accuracy
          </p>
          <div className="mt-[10px]">
            <span className="text-[22px] font-bold leading-none text-black">
              {percent(metrics.top50SkuAccuracy)}
            </span>
          </div>
        </div>
        <OrangeSparkline
          data={metrics.accuracySparkline}
          gradientId="kpiAccuracySparkline"
        />
      </div>

      {/* Row 2, Card 6 */}
      <div className="flex h-[170px] flex-col justify-between rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] pt-[20px] pb-[16px]">
        <div>
          <p className="min-h-[34px] text-[13px] font-medium leading-[1.35] tracking-[-0.011em] text-black/70">
            Restock Rate (vs Last Cycle)
          </p>
          <div className="mt-[10px]">
            <span className="text-[22px] font-bold leading-none text-black">
              {metrics.restockRateDelta ?? NO_VALUE}
            </span>
          </div>
        </div>
        <OrangeSparkline
          data={metrics.restockSparkline}
          gradientId="kpiRestockSparkline"
        />
      </div>
    </div>
  );
}
