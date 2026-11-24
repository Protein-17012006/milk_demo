"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChevronDown, ArrowUp, ArrowDown } from "lucide-react";
import type { ApiReportsSeriesPoint } from "@/lib/api";
import {
  GRANULARITY_OPTIONS,
  bucketStockSeries,
  type ChartGranularity,
  type StockPoint,
} from "@/lib/reports-ui";

interface MonthlyStockChartProps {
  /** Days from GET /reports/series; null while signed out or not loaded. */
  series: ApiReportsSeriesPoint[] | null;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: StockPoint }>;
}

function StockBarTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const item = payload[0].payload;

  return (
    <div className="min-w-[148px] rounded-[8px] border border-[#C6C6C6]/50 bg-white px-3 py-2.5 shadow-[0_6px_20px_rgba(0,0,0,0.08)]">
      <p className="text-[11px] font-medium text-[#252525]">{item.dateLabel}</p>

      <div className="mt-2 space-y-1.5">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[9.5px] text-[#979797]">Avg. units / capture</span>
          <span className="text-[10.5px] font-semibold text-[#4A4A4A]">
            {item.value}
          </span>
        </div>

        <div className="flex items-center justify-between gap-4">
          <span className="text-[9.5px] text-[#979797]">Peak units</span>
          <span className="text-[10.5px] font-semibold text-[#4A4A4A]">
            {item.maxUnits}
          </span>
        </div>

        {item.vsLastPeriod !== null && (
          <div className="flex items-center justify-between gap-4">
            <span className="text-[9.5px] text-[#979797]">vs last period</span>
            <span
              className={`inline-flex items-center gap-0.5 text-[10.5px] font-semibold ${
                item.isPositive ? "text-[#1A932E]" : "text-[#DC2626]"
              }`}
            >
              {item.isPositive ? (
                <ArrowUp className="h-2.5 w-2.5" strokeWidth={2.5} />
              ) : (
                <ArrowDown className="h-2.5 w-2.5" strokeWidth={2.5} />
              )}
              {item.vsLastPeriod}
            </span>
          </div>
        )}
      </div>

      <div className="my-2 h-px bg-[#8F8F8F]/20" />

      <p className="text-center text-[9.5px] font-medium text-[#6B7280]">
        {item.checks.toLocaleString("en-US")} checks
      </p>
    </div>
  );
}

interface PillBarShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  background?: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
  };
}

function PillTrackBarShape({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  background,
}: PillBarShapeProps) {
  const rx = width / 2;
  const trackY = background?.y ?? 0;
  const trackHeight = background?.height ?? 0;

  return (
    <g>
      {trackHeight > 0 && (
        <rect
          x={x}
          y={trackY}
          width={width}
          height={trackHeight}
          rx={rx}
          ry={rx}
          fill="#F2F7FF"
        />
      )}
      {height > 0 && (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          rx={rx}
          ry={rx}
          fill="url(#monthlyBarOrange)"
        />
      )}
    </g>
  );
}

export function MonthlyStockChart({ series }: MonthlyStockChartProps) {
  const [granularity, setGranularity] = useState<ChartGranularity>("Day");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener("mousedown", handleOutside);
    }
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [menuOpen]);

  const chartData = useMemo(
    () => bucketStockSeries(series ?? [], granularity),
    [series, granularity]
  );

  return (
    <div className="flex h-[352px] flex-col rounded-[18px] border border-[#EFF0F6] bg-white px-[22px] pt-[16px] pb-[14px] shadow-[0_4px_18px_rgba(0,0,0,0.05)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#E4E5E7] pb-[12px]">
        <div>
          <h2 className="text-[13px] font-medium tracking-[-0.011em] text-[#4D4D4D]">
            Shelf Stock Count
          </h2>
          <p className="mt-[2px] text-[11px] text-[#9CA3AF]">
            Average units of the store&apos;s expected SKUs per check, opening hours only
          </p>
        </div>

        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((prev) => !prev)}
            className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold text-[#0F2552] hover:bg-black/[0.04] transition-colors cursor-pointer"
          >
            <span>{granularity}</span>
            <ChevronDown
              className={`h-3.5 w-3.5 text-[#0F2552] transition-transform ${
                menuOpen ? "rotate-180" : ""
              }`}
              strokeWidth={2}
            />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-[28px] z-20 w-[110px] rounded-[10px] border border-[#EFF0F6] bg-white p-1 shadow-[0_6px_18px_rgba(0,0,0,0.08)]">
              {GRANULARITY_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => {
                    setGranularity(opt);
                    setMenuOpen(false);
                  }}
                  className={`flex w-full items-center rounded-[7px] px-2.5 py-1.5 text-left text-[12px] transition-colors cursor-pointer ${
                    opt === granularity
                      ? "bg-[#FFF5EC] font-semibold text-[#EE730A]"
                      : "text-black/75 hover:bg-[#F7F7F7]"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bar Chart: one bar per day / ISO week / month of counted checks */}
      {chartData.length === 0 ? (
        <div className="mt-4 flex flex-1 items-center justify-center px-6 text-center text-[12.5px] text-[#9CA3AF]">
          {series === null
            ? "Sign in with an approved account to load the stock history."
            : "No counted checks yet. They start once the store has opening hours in Settings."}
        </div>
      ) : (
      <div className="mt-4 flex-1 min-h-0 w-full overflow-hidden">
        <ResponsiveContainer width="100%" height="100%" debounce={180}>
          <BarChart
            data={chartData}
            margin={{ top: 8, right: 6, left: -24, bottom: 2 }}
            barCategoryGap={chartData.length > 6 ? "30%" : "42%"}
          >
            <defs>
              <linearGradient id="monthlyBarOrange" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#F39237" stopOpacity={0.95} />
                <stop offset="55%" stopColor="#EE730A" stopOpacity={0.92} />
                <stop offset="100%" stopColor="#E66904" stopOpacity={0.95} />
              </linearGradient>
            </defs>

            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#838383", fontSize: 9, fontWeight: 500 }}
              dy={8}
            />
            <YAxis
              domain={[0, "auto"]}
              allowDecimals={false}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "rgba(0,0,0,0.5)", fontSize: 9.5, fontWeight: 600 }}
              dx={-4}
            />
            <Tooltip
              content={<StockBarTooltip />}
              cursor={{ fill: "rgba(242, 247, 255, 0.45)", radius: 8 }}
            />
            <Bar
              dataKey="value"
              barSize={chartData.length > 6 ? 11 : 18}
              fill="url(#monthlyBarOrange)"
              background={{ fill: "transparent" }}
              shape={<PillTrackBarShape />}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      )}
    </div>
  );
}
