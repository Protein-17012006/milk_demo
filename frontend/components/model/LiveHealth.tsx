"use client";

import React, { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ApiModelHealthItem } from "@/lib/api";
import {
  HEALTH_METRICS,
  formatHealth,
  healthChart,
  hourLabel,
  latestHealth,
  type HealthMetric,
} from "@/lib/health-ui";

const CAMERA_COLORS = ["#EE730A", "#2563EB", "#059669", "#7C3AED"];

interface LiveHealthProps {
  health: ApiModelHealthItem[] | null;
  metric: HealthMetric;
  onMetricChange: (metric: HealthMetric) => void;
}

/** Hourly signs of how the counting model is doing, each with what it measures and how to read it. */
export function LiveHealth({ health, metric, onMetricChange }: LiveHealthProps) {
  const info = HEALTH_METRICS.find((m) => m.key === metric) ?? HEALTH_METRICS[0];
  const chart = useMemo(() => healthChart(health ?? [], info.key), [health, info.key]);
  const latest = useMemo(() => latestHealth(health ?? [], info.key), [health, info.key]);
  const yDomain: [number, number | "auto"] =
    info.key === "conf_median" ? [0, 1] : info.percent ? [0, 100] : [0, "auto"];

  return (
    <section data-live-health className="mt-4 rounded-[18px] border border-[#EFF0F6] bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-[620px]">
          <h2 className="text-[15px] font-semibold text-black">Live health, last 7 days</h2>
          <p className="mt-1 text-[12.5px] leading-[1.5] text-[#6B7280]">
            Worked out every hour from the real captures, with no labelling. These numbers warn early that something
            changed; whether the counts are right is what the KPIs above measure.
          </p>
        </div>
        <div role="tablist" aria-label="Health measure" className="flex flex-wrap gap-1">
          {HEALTH_METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              role="tab"
              aria-selected={m.key === info.key}
              onClick={() => onMetricChange(m.key)}
              className={`rounded-[6px] px-2 py-1 text-[12px] cursor-pointer ${m.key === info.key ? "bg-[#111827] text-white" : "text-black/70 hover:bg-black/5"}`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div data-health-explainer className="mt-3 rounded-[12px] bg-[#F7F8FA] px-4 py-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-[13px] font-semibold text-[#111827]">{info.label}</p>
          {latest.length > 0 && (
            <p data-health-latest className="text-[12.5px] text-[#374151]">
              Latest:{" "}
              {latest
                .map((l) => `${formatHealth(info.key, l.value)} at ${l.label}${latest.length > 1 ? ` (${l.camera})` : ""}`)
                .join(", ")}
            </p>
          )}
        </div>
        <p className="mt-1.5 max-w-[78ch] text-[12.5px] leading-[1.55] text-[#374151]">
          <span className="font-medium text-[#111827]">What it measures. </span>
          {info.what}
        </p>
        <p className="mt-1 max-w-[78ch] text-[12.5px] leading-[1.55] text-[#374151]">
          <span className="font-medium text-[#111827]">How to read it. </span>
          {info.read}
        </p>
      </div>

      {health === null ? (
        <p className="mt-4 text-[13px] text-[#6B7280]">Loading the last 7 days…</p>
      ) : chart.rows.length === 0 ? (
        <p className="mt-4 text-[13px] text-[#6B7280]">
          No captures in the last 7 days, so there is nothing to draw. The chart fills in as soon as the counter saves
          captures.
        </p>
      ) : (
        <>
          <div className="mt-3 h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart.rows} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#EFF0F6" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={28} />
                <YAxis domain={yDomain} tick={{ fontSize: 11 }} unit={info.percent ? "%" : undefined} width={48} />
                <Tooltip
                  formatter={(v, name) => [
                    typeof v === "number" ? formatHealth(info.key, v) : "no captures",
                    chart.cameras.length > 1 ? String(name) : info.label,
                  ]}
                />
                {info.reference && (
                  <ReferenceLine
                    y={info.reference.value}
                    stroke="#9CA3AF"
                    strokeDasharray="4 4"
                    label={{ value: info.reference.label, position: "insideTopRight", fontSize: 11, fill: "#6B7280" }}
                  />
                )}
                {chart.cameras.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
                {chart.cameras.map((camera, i) => (
                  <Line
                    key={camera}
                    type="monotone"
                    dataKey={camera}
                    name={camera}
                    stroke={CAMERA_COLORS[i % CAMERA_COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 2 }}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <HealthTotals health={health} />
        </>
      )}
    </section>
  );
}

/** One plain sentence on how much data the chart rests on, duplicate boxes and the model versions seen. */
function HealthTotals({ health }: { health: ApiModelHealthItem[] }) {
  const captures = health.reduce((s, h) => s + h.captures, 0);
  const hours = [...new Set(health.map((h) => h.hour))].sort();
  const lastHour = hours[hours.length - 1];
  const duplicates = health.filter((h) => h.hour === lastHour).reduce((s, h) => s + (h.duplicate_pairs ?? 0), 0);
  const versions = [...new Set(health.flatMap((h) => h.model_versions ?? []))].map((v) =>
    v === "unknown" ? "not recorded (older captures)" : v
  );
  return (
    <p data-health-totals className="mt-3 max-w-[110ch] text-[12px] leading-[1.5] text-[#6B7280]">
      {captures.toLocaleString("en-US")} captures over {hours.length} {hours.length === 1 ? "hour" : "hours"} with
      data. In the latest hour ({hourLabel(lastHour)}), {duplicates} {duplicates === 1 ? "pair" : "pairs"} of boxes sat
      on the same item (should be 0). Model {versions.length === 1 ? "version" : "versions"}: {versions.join(", ")}.
    </p>
  );
}
