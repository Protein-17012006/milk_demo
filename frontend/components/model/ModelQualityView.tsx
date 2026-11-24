"use client";

import React, { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Tag } from "lucide-react";
import { useAuth } from "@/lib/auth";
import {
  createApiClient,
  type ApiAuditListItem,
  type ApiModelHealthItem,
  type ApiModelSummary,
} from "@/lib/api";
import { KPI_ORDER, kpiDisplay, pct, type Tone } from "@/lib/model-ui";
import type { HealthMetric } from "@/lib/health-ui";
import { AuditLabeler } from "./AuditLabeler";
import { LiveHealth } from "./LiveHealth";

const RANGES: { days: number; label: string }[] = [
  { days: 7, label: "Last 7 days" },
  { days: 30, label: "Last 30 days" },
  { days: 0, label: "All time" },
];
const TONE: Record<Tone, string> = { met: "#15803D", missed: "#B91C1C", none: "#6B7280" };
const CARD = "rounded-[18px] border border-[#EFF0F6] bg-white";

/**
 * The Model page: Datagent's 12 KPIs from frames the team labelled, errors per SKU, the confusion matrix, the
 * daily trend and the live health of the last 7 days. Spec docs/superpowers/specs/2026-11-23-model-quality-page-design.md.
 */
export function ModelQualityView() {
  const { isApproved, hasGroup, getIdToken } = useAuth();
  const allowed = isApproved && hasGroup("team_admin", "field_team");
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);
  const [days, setDays] = useState(7);
  const [version, setVersion] = useState("all");
  const [summary, setSummary] = useState<ApiModelSummary | null>(null);
  const [health, setHealth] = useState<ApiModelHealthItem[] | null>(null);
  const [pending, setPending] = useState<ApiAuditListItem[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [labelling, setLabelling] = useState<string[] | null>(null);
  const [healthMetric, setHealthMetric] = useState<HealthMetric>("conf_median");
  const [reloadKey, setReloadKey] = useState(0); // bumped after a save or a skip

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    Promise.all([api.getModelSummary(days, version), api.getModelHealth(7), api.listAudits("pending", 0)])
      .then(([s, h, p]) => {
        if (cancelled) return;
        setSummary(s);
        setHealth(h.items);
        setPending(p.items);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [allowed, api, days, version, reloadKey]);

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    api
      .getProducts()
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, string> = {};
        for (const p of res.items) if (p.model_alias) map[p.model_alias] = p.sku_name;
        setNames(map);
      })
      .catch(() => undefined); // names are a nicety: model labels are shown instead
    return () => {
      cancelled = true;
    };
  }, [allowed, api]);

  const nameOf = (label: string) =>
    ({ UNRECOGNIZED: "Unrecognized", MISSED: "Missed by model", NOT_PRODUCT: "Not our SKU", OTHER_GOODS: "Other goods" } as Record<string, string>)[label] ??
    names[label] ??
    label;

  if (!isApproved || !allowed) {
    return (
      <div className="mx-auto w-full px-4 pt-6 pb-8 sm:px-6 lg:px-7">
        <h1 className="border-b border-black/10 pb-[18px] text-[22px] font-normal text-black">Model</h1>
        <p data-model-denied className="mt-6 text-[14px] text-[#6B7280]">
          The Model page is for team_admin and field_team accounts. Sign in with one of them to label frames and
          see how the model scores.
        </p>
      </div>
    );
  }

  // scoring frames first, then training frames; each group oldest first
  const oldestFirst = [...pending].sort(
    (a, b) =>
      Number(a.purpose === "training") - Number(b.purpose === "training") ||
      a.capture_timestamp.localeCompare(b.capture_timestamp)
  );
  const versions = summary?.model_versions ?? [];

  return (
    <div className="mx-auto w-full px-4 pt-6 pb-8 sm:px-6 lg:px-7">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-black/10 pb-[18px]">
        <div>
          <h1 className="text-[22px] font-normal leading-tight text-black">Model</h1>
          <p className="mt-1 text-[12px] text-[#6B7280]">
            Datagent&apos;s Accuracy Report from frames the team labelled
            {summary ? ` · ${summary.n_audits} labelled ${summary.n_audits === 1 ? "frame" : "frames"}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <select aria-label="Model version" value={version} onChange={(e) => setVersion(e.target.value)}
            className="rounded-[8px] border border-black/15 bg-white px-2.5 py-1.5">
            <option value="all">All versions</option>
            {versions.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <select aria-label="Range" value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-[8px] border border-black/15 bg-white px-2.5 py-1.5">
            {RANGES.map((r) => (
              <option key={r.days} value={r.days}>
                {r.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-label-frames
            disabled={pending.length === 0}
            onClick={() => setLabelling(oldestFirst.map((a) => a.audit_id))}
            className="inline-flex items-center gap-1.5 rounded-[8px] bg-[#EE730A] px-3 py-1.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
          >
            <Tag className="h-4 w-4" />
            Label frames ({pending.length} pending)
          </button>
        </div>
      </header>

      {error && <p className="mt-4 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-[13px] text-[#991B1B]">{error}</p>}

      {summary && summary.old_rule_frames > 0 && (
        <p data-old-rule-frames className="mt-4 rounded-[8px] bg-[#FFF7ED] px-3 py-2 text-[13px] text-[#7C2D12]">
          {summary.old_rule_frames} frames were labelled before rule A — relabel them so the numbers follow one rule
        </p>
      )}

      <section className="mt-5">
        <h2 className="mb-2 text-[15px] font-semibold text-black">Datagent KPIs</h2>
        {summary && summary.out_of_scope_share.n > 0 && (
          <p data-out-of-scope-share className="mb-3 text-[13px] text-[#6B7280]">
            Out of scope boxes: {pct(summary.out_of_scope_share.value)} of {summary.out_of_scope_share.n} boxes
          </p>
        )}
        {summary && summary.n_audits === 0 && (
          <p data-no-labels className="mb-3 text-[13px] text-[#6B7280]">
            No labelled frames yet. Label the sampled frames to fill these numbers.
          </p>
        )}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {KPI_ORDER.map(({ name, label, hint }) => {
            const kpi = summary?.kpis[name];
            const shown = kpi ? kpiDisplay(name, kpi) : { text: "—", targetText: "", tone: "none" as Tone };
            return (
              <div key={name} data-kpi={name} title={hint} className={`${CARD} px-4 py-3.5`}>
                <p className="text-[12.5px] font-medium leading-snug text-black/70">{label}</p>
                <p data-kpi-value className="mt-2 text-[22px] font-bold leading-none" style={{ color: TONE[shown.tone] }}>
                  {shown.text}
                </p>
                <p className="mt-1.5 text-[11.5px] text-[#6B7280]">
                  Target {shown.targetText}
                  {kpi && kpi.n > 0 ? ` · n = ${kpi.n}` : ""}
                </p>
                {name === "minor_error_rate" && kpi && (
                  <p className="text-[11.5px] text-[#6B7280]">Exact + minor {pct(kpi.exact_or_minor)}</p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className={`${CARD} p-4`}>
          <h2 className="mb-2 text-[15px] font-semibold text-black">Per SKU</h2>
          {!summary || summary.per_sku.length === 0 ? (
            <p className="text-[13px] text-[#6B7280]">—</p>
          ) : (
            <table data-per-sku className="w-full text-left text-[13px]">
              <thead className="text-[11.5px] text-[#6B7280]">
                <tr>
                  <th className="py-1 font-medium">SKU</th>
                  <th className="text-right font-medium">Model</th>
                  <th className="text-right font-medium">Truth</th>
                  <th className="text-right font-medium">Named right</th>
                  <th className="text-right font-medium">Missed</th>
                  <th className="pl-3 font-medium">Mostly mistaken for</th>
                </tr>
              </thead>
              <tbody>
                {summary.per_sku.map((r) => (
                  <tr key={r.sku_id} className="border-t border-black/5">
                    <td className="py-1.5 pr-2">{nameOf(r.sku_id)}</td>
                    <td className="text-right">{r.model_units}</td>
                    <td className="text-right">{r.true_units}</td>
                    <td className="text-right">{pct(r.id_accuracy)}</td>
                    <td className="text-right">{r.missed_units}</td>
                    <td className="pl-3 text-[#B91C1C]">
                      {r.confused_as ? `${nameOf(r.confused_as)} (${r.confused_count})` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className={`${CARD} p-4`}>
          <h2 className="mb-2 text-[15px] font-semibold text-black">Confusion (model → truth)</h2>
          {!summary || summary.confusion.rows.length === 0 ? (
            <p className="text-[13px] text-[#6B7280]">—</p>
          ) : (
            <div className="overflow-x-auto">
              <table data-confusion className="text-[12px]">
                <thead>
                  <tr>
                    <th className="p-1.5 text-left font-medium text-[#6B7280]">Model said ↓ / truth →</th>
                    {summary.confusion.cols.map((c) => (
                      <th key={c} className="max-w-[90px] p-1.5 text-center font-medium text-[#6B7280]">
                        {nameOf(c)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {summary.confusion.rows.map((r) => (
                    <tr key={r}>
                      <th className="p-1.5 text-left font-medium">{nameOf(r)}</th>
                      {summary.confusion.cols.map((c) => {
                        const n = summary.confusion.cells[`${r}|${c}`] ?? 0;
                        const right = r === c || (r === "UNRECOGNIZED" && c === "OTHER_GOODS");
                        const bg = n === 0 ? "transparent" : right ? `rgba(22,163,74,${Math.min(0.15 + n * 0.08, 0.6)})` : `rgba(220,38,38,${Math.min(0.15 + n * 0.08, 0.6)})`;
                        return (
                          <td key={c} className="min-w-[42px] p-1.5 text-center" style={{ background: bg }}>
                            {n || ""}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section className={`${CARD} mt-4 p-4`}>
        <h2 className="mb-2 text-[15px] font-semibold text-black">By day</h2>
        {!summary || summary.by_day.length === 0 ? (
          <p className="text-[13px] text-[#6B7280]">—</p>
        ) : (
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={summary.by_day.map((d) => ({
                  day: d.day.slice(5),
                  identification: d.overall_identification_accuracy === null ? null : d.overall_identification_accuracy * 100,
                  exactOrMinor: d.exact_or_minor_rate === null ? null : d.exact_or_minor_rate * 100,
                  frames: d.audits,
                }))}
                margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid stroke="#EFF0F6" />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => (typeof v === "number" ? `${v.toFixed(1)}%` : String(v))} />
                <Line type="monotone" dataKey="identification" name="Identification" stroke="#EE730A" strokeWidth={2} isAnimationActive={false} connectNulls />
                <Line type="monotone" dataKey="exactOrMinor" name="Exact + minor" stroke="#2563EB" strokeWidth={2} isAnimationActive={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <LiveHealth health={health} metric={healthMetric} onMetricChange={setHealthMetric} />

      {labelling && (
        <AuditLabeler auditIds={labelling} onClose={() => setLabelling(null)} onChanged={() => setReloadKey((k) => k + 1)} />
      )}
    </div>
  );
}
