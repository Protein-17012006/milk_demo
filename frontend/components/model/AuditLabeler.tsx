"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, X, ZoomIn } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { createApiClient, type ApiAuditDetail } from "@/lib/api";
import { focusRegion, type Box } from "@/lib/frame-geometry";
import {
  canSave,
  nextVerdict,
  toPayload,
  totalsBySku,
  type BoxLabel,
  type MissedPoint,
  type Verdict,
} from "@/lib/audit-labeling";

const VERDICT_STYLE: Record<string, { color: string; label: string }> = {
  none: { color: "#9CA3AF", label: "Not judged" },
  correct: { color: "#16A34A", label: "Right" },
  wrong_sku: { color: "#DC2626", label: "Wrong SKU" },
  not_product: { color: "#7C3AED", label: "Not our SKU" },
  out_of_scope: { color: "#6B7280", label: "Out of scope" },
};
const MISSED_COLOR = "#EE730A";
const SKIP_REASONS: { value: string; label: string }[] = [
  { value: "blurry", label: "Blurry frame" },
  { value: "blocked", label: "Shelf blocked (person, object)" },
  { value: "camera_moved", label: "Camera moved" },
  { value: "display_away", label: "Display not in view" },
  { value: "other", label: "Other" },
];

interface AuditLabelerProps {
  /** Audits to label, oldest first: pending ones, or done ones to relabel under the current rule (their saved verdicts load
   * first). Next moves along this list. */
  auditIds: string[];
  onClose(): void;
  /** Called after a save or a skip, so the page can reload its numbers. */
  onChanged(): void;
}

/**
 * Labels one sampled frame at a time: click a box to cycle Right → Wrong SKU → Not our SKU → Out of scope, pick the right
 * SKU for wrong boxes, click empty shelf to add a unit the model missed. Spec 2026-11-23, section 7.
 */
export function AuditLabeler({ auditIds, onClose, onChanged }: AuditLabelerProps) {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);
  const [index, setIndex] = useState(0);
  const [detail, setDetail] = useState<ApiAuditDetail | null>(null);
  const [labels, setLabels] = useState<Record<number, BoxLabel>>({});
  const [missed, setMissed] = useState<MissedPoint[]>([]);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [zoomed, setZoomed] = useState(true);
  const [pendingPoint, setPendingPoint] = useState<{ x: number; y: number } | null>(null);
  const [skipping, setSkipping] = useState(false);
  const [skipReason, setSkipReason] = useState("blocked");
  const [skipNote, setSkipNote] = useState("");
  const [missesChecked, setMissesChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0); // bumped to fetch a fresh signed link
  const reloadedRef = useRef(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const auditId = auditIds[index];

  useEffect(() => {
    if (!auditId) return;
    let cancelled = false;
    api
      .getAudit(auditId)
      .then((d) => {
        if (cancelled) return;
        const fromSaved: Record<number, BoxLabel> = {};
        for (const v of d.verdicts) fromSaved[v.box_id] = { verdict: v.verdict, trueSku: v.true_sku_id ?? null };
        setDetail(d);
        setLabels(fromSaved);
        setMissed(d.missed.map((m) => ({ ...m })));
        setMessage(null);
      })
      .catch((err) => {
        if (!cancelled) setMessage(`Could not open ${auditId}: ${err instanceof Error ? err.message : String(err)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [api, auditId, reloadTick]);

  // The frame's real size comes from the image itself; an expired link (15 min) is fetched again once.
  useEffect(() => {
    if (!detail?.frame_url) return;
    let alive = true;
    const img = new window.Image();
    img.onload = () => {
      if (alive) setSize({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => {
      if (!alive) return;
      if (!reloadedRef.current) {
        reloadedRef.current = true;
        setReloadTick((t) => t + 1);
      } else {
        setMessage("The frame could not be loaded. Close and open the frame again.");
      }
    };
    img.src = detail.frame_url;
    return () => {
      alive = false;
      img.onload = null;
      img.onerror = null;
    };
  }, [detail]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const names = useMemo(() => {
    const map: Record<string, string> = {};
    for (const c of detail?.sku_choices ?? []) map[c.label] = c.name;
    return map;
  }, [detail]);
  const nameOf = (label: string | null) => (label ? names[label] ?? label : "Unrecognized");

  const boxes = useMemo(() => detail?.ai_boxes ?? [], [detail]);
  const region = useMemo(() => {
    if (!size) return null;
    const frameBoxes: Box[] = boxes.map((b) => b.box);
    return zoomed ? focusRegion(frameBoxes, size.w, size.h) : { x: 0, y: 0, w: size.w, h: size.h };
  }, [size, zoomed, boxes]);
  const fontSize = region ? region.w / 50 : 0;
  const totals = useMemo(() => totalsBySku(boxes, labels, missed), [boxes, labels, missed]);
  const saveAllowed = detail !== null && canSave(boxes, labels, missesChecked) && !busy;

  const setVerdict = (boxId: number, verdict: Verdict | null) =>
    setLabels((prev) => ({ ...prev, [boxId]: { verdict, trueSku: prev[boxId]?.trueSku ?? null } }));
  const setTrueSku = (boxId: number, sku: string) =>
    setLabels((prev) => ({ ...prev, [boxId]: { verdict: "wrong_sku", trueSku: sku || null } }));

  const onCanvasClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const target = e.target as Element;
    if (target.closest("[data-box]") || target.closest("[data-missed]")) return;
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return;
    const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    setPendingPoint({ x: pt.x, y: pt.y });
  };

  const goNext = () => {
    if (index + 1 >= auditIds.length) {
      onClose();
      return;
    }
    setDetail(null);
    setSize(null);
    setLabels({});
    setMissed([]);
    setMissesChecked(false);
    setPendingPoint(null);
    setSkipping(false);
    setMessage(null);
    reloadedRef.current = false;
    setIndex(index + 1);
  };

  const save = async () => {
    if (!detail || !saveAllowed) return;
    setBusy(true);
    try {
      await api.saveAudit(detail.audit_id, toPayload(labels, missed));
      onChanged();
      goNext();
    } catch (err) {
      setMessage(`Not saved: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  const skip = async () => {
    if (!detail) return;
    setBusy(true);
    try {
      await api.skipAudit(detail.audit_id, skipReason, skipNote);
      onChanged();
      goNext();
    } catch (err) {
      setMessage(`Not skipped: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div
      data-audit-labeler
      role="dialog"
      aria-modal="true"
      aria-label="Label a frame"
      className="fixed inset-0 z-[60] flex flex-col bg-black/85"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#111827] px-5 py-3 text-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
          <span className="font-semibold">
            Frame {Math.min(index + 1, auditIds.length)} of {auditIds.length}
          </span>
          {detail && (
            <>
              <span className="font-semibold">
                {detail.purpose === "review"
                  ? "Review frame — machine-unsure cans; your choice teaches the auto-labeller, never scored"
                  : detail.purpose === "training"
                    ? "Training frame — teaches the flavour gallery, never scored"
                    : "Scoring frame — counts in the accuracy numbers"}
              </span>
              <span className="font-mono text-[12px]">{detail.capture_id}</span>
              <span className="text-white/70">{detail.capture_timestamp}</span>
              <span className="text-white/70">Model {detail.model_version}</span>
              <span>
                {boxes.length} {boxes.length === 1 ? "box" : "boxes"}
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setZoomed((z) => !z)}
            className="inline-flex items-center gap-1.5 rounded-[6px] border border-white/25 px-2.5 py-1 text-[12px] font-medium hover:bg-white/10 cursor-pointer"
          >
            {zoomed ? <Maximize2 className="h-3.5 w-3.5" /> : <ZoomIn className="h-3.5 w-3.5" />}
            {zoomed ? "Full frame" : "Zoom to boxes"}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close labelling"
            className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-white/10 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {message && (
        <p data-labeler-message className="bg-[#FFF7ED] px-5 py-2 text-[12.5px] text-[#7C2D12]">
          {message}
        </p>
      )}

      <p data-rule-a className="bg-[#F3F4F6] px-5 py-2 text-[12.5px] text-[#1F2937]">
        <b>Rule B</b> — count every unit of the store&apos;s shelf plan (can, carton, pack) whose face, lid or top
        shows enough to tell the product. Mark <b>Out of scope</b>: units almost fully hidden, units whose product you
        can&apos;t tell.
      </p>

      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
        <div className="flex min-h-[300px] flex-1 items-center justify-center">
          {detail && region && size ? (
            <svg
              ref={svgRef}
              data-labeler-frame
              viewBox={`${region.x} ${region.y} ${region.w} ${region.h}`}
              preserveAspectRatio="xMidYMid meet"
              className="h-full w-full cursor-crosshair"
              onClick={onCanvasClick}
              role="img"
              aria-label={`Frame with ${boxes.length} boxes`}
            >
              <image href={detail.frame_url ?? ""} x={0} y={0} width={size.w} height={size.h} />
              {boxes.map((b) => {
                const style = VERDICT_STYLE[labels[b.box_id]?.verdict ?? "none"];
                const [x, y, w, h] = b.box;
                return (
                  <g
                    key={b.box_id}
                    data-box={b.box_id}
                    className="cursor-pointer"
                    onClick={() => setVerdict(b.box_id, nextVerdict(labels[b.box_id]?.verdict ?? null, b.needs_flavour))}
                  >
                    <rect x={x} y={y} width={w} height={h} fill={style.color} fillOpacity={0.12}
                      stroke={style.color} strokeWidth={3} vectorEffect="non-scaling-stroke" />
                    <text x={x} y={Math.max(y - fontSize * 0.3, fontSize)} fontSize={fontSize} fontWeight={700}
                      fill={style.color} stroke="#FFFFFF" strokeWidth={fontSize / 6} paintOrder="stroke">
                      {b.needs_flavour ? `${b.box_id}?` : b.box_id}
                    </text>
                  </g>
                );
              })}
              {missed.map((m, i) => (
                <circle
                  key={`${i}-${m.x}-${m.y}`}
                  data-missed={i}
                  cx={m.x}
                  cy={m.y}
                  r={fontSize * 0.45}
                  fill={MISSED_COLOR}
                  stroke="#FFFFFF"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                  className="cursor-pointer"
                  onClick={() => setMissed((prev) => prev.filter((_, j) => j !== i))}
                />
              ))}
              {pendingPoint && (
                <circle cx={pendingPoint.x} cy={pendingPoint.y} r={fontSize * 0.45} fill="none"
                  stroke={MISSED_COLOR} strokeWidth={3} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
              )}
            </svg>
          ) : (
            <p className="text-[13px] text-white/70">{detail ? "Loading frame…" : "Loading…"}</p>
          )}
        </div>

        <aside className="flex w-full shrink-0 flex-col gap-3 overflow-y-auto rounded-[12px] bg-white p-4 text-[13px] lg:w-[360px]">
          <p className="text-[12px] leading-snug text-[#6B7280]">
            Click a box to cycle <b className="text-[#16A34A]">Right</b> → <b className="text-[#DC2626]">Wrong SKU</b> →{" "}
            <b className="text-[#7C3AED]">Not our SKU</b> → <b className="text-[#6B7280]">Out of scope</b>. Click empty shelf to add a unit the model missed; click an
            orange dot to remove it.
            {detail?.purpose === "review" && (
              <> A ? box has no suggestion: click to pick its flavour, Not our SKU or Out of scope.</>
            )}
          </p>

          {pendingPoint && (
            <div data-missed-picker className="rounded-[8px] border border-[#FED7AA] bg-[#FFF7ED] p-2.5">
              <p className="mb-1.5 font-medium">Which SKU did the model miss here?</p>
              <div className="flex gap-2">
                <select
                  aria-label="Missed SKU"
                  className="min-w-0 flex-1 rounded-[6px] border border-black/15 px-2 py-1"
                  defaultValue=""
                  onChange={(e) => {
                    if (!e.target.value) return;
                    setMissed((prev) => [...prev, { sku_id: e.target.value, ...pendingPoint }]);
                    setPendingPoint(null);
                  }}
                >
                  <option value="">Choose…</option>
                  {detail?.sku_choices.map((c) => (
                    <option key={c.label} value={c.label}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <button type="button" onClick={() => setPendingPoint(null)}
                  className="rounded-[6px] px-2 py-1 text-[12px] text-[#6B7280] hover:bg-black/5 cursor-pointer">
                  Cancel
                </button>
              </div>
            </div>
          )}

          <section>
            <h3 className="mb-1.5 text-[12px] font-semibold uppercase tracking-wide text-[#6B7280]">Model boxes</h3>
            {boxes.length === 0 && <p className="text-[#6B7280]">The model drew no box on this frame.</p>}
            <ul className="flex flex-col gap-1.5">
              {boxes.map((b) => {
                const label = labels[b.box_id];
                const verdict = label?.verdict ?? null;
                return (
                  <li key={b.box_id} data-box-row={b.box_id} className="rounded-[8px] border border-black/10 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate">
                        <b>#{b.box_id}</b> {b.needs_flavour ? "? no suggestion" : nameOf(b.sku_id)}{" "}
                        {!b.needs_flavour && <span className="text-[#6B7280]">· {b.conf.toFixed(2)}</span>}
                      </span>
                      <span className="shrink-0 text-[11.5px] font-semibold" style={{ color: VERDICT_STYLE[verdict ?? "none"].color }}>
                        {b.needs_flavour && verdict === "wrong_sku" ? "Flavour" : VERDICT_STYLE[verdict ?? "none"].label}
                      </span>
                    </div>
                    <div className="mt-1.5 flex gap-1">
                      {(["correct", "wrong_sku", "not_product", "out_of_scope"] as Verdict[])
                        .filter((v) => !(b.needs_flavour && v === "correct"))
                        .map((v) => (
                        <button
                          key={v}
                          type="button"
                          data-verdict={v}
                          onClick={() => setVerdict(b.box_id, v)}
                          className={`flex-1 rounded-[6px] border px-1.5 py-0.5 text-[11.5px] cursor-pointer ${
                            verdict === v ? "text-white" : "bg-white text-black/70 hover:bg-black/5"
                          }`}
                          style={verdict === v ? { background: VERDICT_STYLE[v].color, borderColor: VERDICT_STYLE[v].color } : undefined}
                        >
                          {b.needs_flavour && v === "wrong_sku" ? "Flavour" : VERDICT_STYLE[v].label}
                        </button>
                      ))}
                    </div>
                    {verdict === "wrong_sku" && (
                      <select
                        aria-label={b.needs_flavour ? `Flavour for box ${b.box_id}` : `Right SKU for box ${b.box_id}`}
                        className="mt-1.5 w-full rounded-[6px] border border-black/15 px-2 py-1"
                        value={label?.trueSku ?? ""}
                        onChange={(e) => setTrueSku(b.box_id, e.target.value)}
                      >
                        <option value="">{b.needs_flavour ? "Which flavour?" : "What is it really?"}</option>
                        {detail?.sku_choices
                          .filter((c) => c.label !== b.sku_id)
                          .map((c) => (
                            <option key={c.label} value={c.label}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          <section>
            <h3 className="mb-1.5 text-[12px] font-semibold uppercase tracking-wide text-[#6B7280]">Per SKU</h3>
            {Object.keys(totals).length === 0 ? (
              <p className="text-[#6B7280]">Nothing counted yet.</p>
            ) : (
              <table data-labeler-totals className="w-full text-left">
                <thead className="text-[11.5px] text-[#6B7280]">
                  <tr>
                    <th className="font-medium">SKU</th>
                    <th className="w-14 text-right font-medium">Model</th>
                    <th className="w-14 text-right font-medium">Truth</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(totals).map(([sku, t]) => (
                    <tr key={sku} className={t.model !== t.truth ? "text-[#B91C1C]" : ""}>
                      <td className="truncate py-0.5">{nameOf(sku)}</td>
                      <td className="text-right">{t.model}</td>
                      <td className="text-right">{t.truth}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {skipping ? (
            <div className="flex flex-col gap-2 rounded-[8px] border border-black/10 p-2.5">
              <select aria-label="Skip reason" value={skipReason} onChange={(e) => setSkipReason(e.target.value)}
                className="rounded-[6px] border border-black/15 px-2 py-1">
                {SKIP_REASONS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <input aria-label="Skip note" value={skipNote} onChange={(e) => setSkipNote(e.target.value)}
                placeholder="Note (optional)" className="rounded-[6px] border border-black/15 px-2 py-1" />
              <div className="flex gap-2">
                <button type="button" disabled={busy} onClick={() => void skip()}
                  className="flex-1 rounded-[8px] bg-[#111827] px-3 py-1.5 font-semibold text-white disabled:opacity-40 cursor-pointer">
                  Skip this frame
                </button>
                <button type="button" onClick={() => setSkipping(false)}
                  className="rounded-[8px] px-3 py-1.5 text-[#6B7280] hover:bg-black/5 cursor-pointer">
                  Back
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-auto flex flex-wrap gap-2 pt-1">
              <label className="flex w-full items-start gap-2 text-[12.5px]">
                <input
                  type="checkbox"
                  data-misses-checked
                  checked={missesChecked}
                  onChange={(e) => setMissesChecked(e.target.checked)}
                  className="mt-0.5 cursor-pointer"
                />
                <span>I checked for cans the model missed (click the shelf to add them)</span>
              </label>
              <button
                type="button"
                data-save
                disabled={!saveAllowed}
                onClick={() => void save()}
                title={saveAllowed ? undefined : "Judge every box, pick the right SKU for wrong ones, and tick the missed-cans check"}
                className="flex-1 rounded-[8px] bg-[#EE730A] px-3 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
              >
                {busy ? "Saving…" : "Save"}
              </button>
              <button type="button" disabled={!detail || busy} onClick={() => setSkipping(true)}
                className="rounded-[8px] border border-black/15 px-3 py-2 font-medium hover:bg-black/5 disabled:opacity-40 cursor-pointer">
                Skip…
              </button>
              <button type="button" onClick={goNext}
                className="rounded-[8px] px-3 py-2 text-[#6B7280] hover:bg-black/5 cursor-pointer">
                Next
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>,
    document.body
  );
}
