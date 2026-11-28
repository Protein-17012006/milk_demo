"use client";

import React, { useEffect, useState } from "react";
import type { ApiLabellers } from "@/lib/api";
import { pct } from "@/lib/model-ui";

interface LabellerAgreementProps {
  /** GET /model/labellers: the backend answers team admins only. */
  load: () => Promise<ApiLabellers>;
  /** PUT /model/audits/{id}/answer-key. */
  setKey: (auditId: string, on: boolean) => Promise<unknown>;
  /** Bumped by the page after a save in the labeller, so a new answer key or a new result shows. */
  reloadKey: number;
}

/** "2026-11-28T09:04:28+07:00" as "28/11 09:04", the time on the camera (UTC+7). */
const when = (ts?: string) => (ts && ts.length >= 16 ? `${ts.slice(8, 10)}/${ts.slice(5, 7)} ${ts.slice(11, 16)}` : "—");

/**
 * For team admins: how far each labeller's answers agree with the answer keys, by week, and the answer keys there
 * are (operations-loop design 5.4). After every nine frames a labeller saves, the next one in their queue is a
 * check: a frame a team admin labelled with care and marked. Labellers are not told which frames are checks, so
 * nothing on this page links to one.
 */
export function LabellerAgreement({ load, setKey, reloadKey }: LabellerAgreementProps) {
  const [data, setData] = useState<ApiLabellers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [load, reloadKey, tick]);

  const remove = async (auditId: string) => {
    setRemoving(auditId);
    try {
      await setKey(auditId, false);
      setTick((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRemoving(null);
    }
  };

  if (!data && !error) return null;

  return (
    <section
      data-labeller-agreement
      className="mt-4 rounded-[18px] border border-[#EFF0F6] bg-white px-4 py-3.5 text-[13px] text-[#111827]"
    >
      <h2 className="text-[14px] font-semibold">Labeller agreement</h2>
      <p className="mt-1 text-[12.5px] leading-[1.5] text-[#6B7280]">
        Agreement with the answer keys on check frames: after every {(data?.check_every ?? 10) - 1} frames a labeller
        saves, the next one is a check. Labellers are not told which frames are checks. Only team admins see this
        block.
      </p>
      {error && <p className="mt-2 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-[12.5px] text-[#991B1B]">{error}</p>}

      {data && data.rows.length === 0 && (
        <p data-no-agreement className="mt-3 text-[12.5px] text-[#374151]">
          {data.keys.length === 0
            ? "No answer keys yet. Label a frame with care, then tick 'Use as answer key'."
            : "No check frame has been answered yet."}
        </p>
      )}

      {data && data.rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[420px] text-left text-[12.5px]">
            <thead className="text-[#6B7280]">
              <tr>
                <th className="py-1 pr-3 font-medium">Labeller</th>
                <th className="py-1 pr-3 font-medium">Week</th>
                <th className="py-1 pr-3 font-medium">Check frames</th>
                <th className="py-1 pr-3 font-medium">Units that agree</th>
                <th className="py-1 font-medium">Agreement</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={`${r.labeller}|${r.week}`} data-agreement-row className="border-t border-black/5">
                  <td className="py-1 pr-3">{r.labeller}</td>
                  <td className="py-1 pr-3">{r.week}</td>
                  <td className="py-1 pr-3">{r.frames}</td>
                  <td className="py-1 pr-3">
                    {r.agree} of {r.units}
                  </td>
                  <td className="py-1 font-semibold">{pct(r.agreement)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.keys.length > 0 && (
        <details className="mt-3 text-[12.5px] text-[#374151]">
          <summary className="cursor-pointer select-none">
            Answer keys ({data.keys.length})
          </summary>
          <ul className="mt-1 flex flex-col gap-[4px]">
            {data.keys.map((k) => (
              <li key={k.audit_id} data-answer-key-row className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span>
                  Frame of {when(k.capture_timestamp)}, marked by {k.answer_key_by ?? "—"} on {when(k.answer_key_at)} ·{" "}
                  {k.sheets_done} answered, {k.sheets_pending} waiting
                </span>
                <button
                  type="button"
                  disabled={removing !== null}
                  onClick={() => void remove(k.audit_id)}
                  className="rounded-[6px] border border-black/15 px-2 py-[2px] text-[12px] hover:bg-black/5 disabled:opacity-40 cursor-pointer"
                >
                  {removing === k.audit_id ? "Removing…" : "Remove"}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
