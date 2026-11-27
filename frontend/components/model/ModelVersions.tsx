"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import type { ApiCameraVersions, ApiModelVersions, VersionAction } from "@/lib/api";
import {
  canPutLive,
  pollDelay,
  requestStatus,
  runLine,
  runnerQuiet,
  sinceText,
  skuRows,
  statusText,
  verdictText,
} from "@/lib/model-versions";

interface ModelVersionsProps {
  load: () => Promise<ApiModelVersions>;
  send: (body: { camera_id: string; action: VersionAction; version_id?: string }) => Promise<unknown>;
  isAdmin: boolean;
  /** Product names for model labels. */
  names: Record<string, string>;
}

interface Asking {
  cameraId: string;
  action: VersionAction;
  versionId?: string;
  question: string;
}

const RESTART_NOTE = "The counting worker restarts; counting pauses for about a minute.";
const VERDICT_TONE: Record<string, string> = {
  better: "text-[#15803D]",
  worse: "text-[#B91C1C]",
  no_difference: "text-[#374151]",
  waiting: "text-[#6B7280]",
};

/**
 * The live model version of each camera, the candidate that runs in parallel with it, how people's answers on the
 * labelled frames compare the two, and (team admin) the three requests: put the candidate live, discard it, roll back.
 * The counting machine carries a request out; this block shows it waiting until that machine has answered.
 */
export function ModelVersions({ load, send, isAdmin, names }: ModelVersionsProps) {
  const [data, setData] = useState<ApiCameraVersions[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [sending, setSending] = useState(false);
  const [tick, setTick] = useState(0);
  const [readAt, setReadAt] = useState(0); // when the data on screen was read: the clock the block judges by

  useEffect(() => {
    let cancelled = false;
    load()
      .then((res) => {
        if (cancelled) return;
        setData(res.cameras);
        setReadAt(Date.now());
      })
      .catch(() => {
        // the rest of the Model page does not depend on this block: it stays hidden until it can be read
        if (!cancelled) setData((old) => old ?? []);
      });
    return () => {
      cancelled = true;
    };
  }, [load, tick]);

  // while a request waits for a counting machine that gives signs of life, look again every few seconds, for
  // two minutes at most; otherwise once a minute
  const waiting = (data ?? []).some((c) => requestStatus(c.state).kind === "waiting");
  const waitingSince = useRef<number | null>(null);
  useEffect(() => {
    const now = Date.now();
    if (!waiting) waitingSince.current = null;
    else if (waitingSince.current === null) waitingSince.current = now;
    const quiet = (data ?? []).every((c) => runnerQuiet(c.state.runner_seen_at, now));
    const delay = pollDelay({ waiting, quiet, waitedMs: waitingSince.current === null ? 0 : now - waitingSince.current });
    const timer = setTimeout(() => setTick((n) => n + 1), delay);
    return () => clearTimeout(timer);
  }, [waiting, tick, data]);

  const confirm = useCallback(async () => {
    if (!asking) return;
    setSending(true);
    setError(null);
    try {
      await send({ camera_id: asking.cameraId, action: asking.action, version_id: asking.versionId });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request could not be sent.");
    } finally {
      setSending(false);
      setAsking(null);
      setTick((n) => n + 1);
    }
  }, [asking, send]);

  if (!data || data.length === 0) return null;

  return (
    <section className="mt-4 flex flex-col gap-3">
      {data.map((camera) => {
        const { state, candidate, versions } = camera;
        const liveRow = versions.find((v) => v.version_id === state.live);
        const request = requestStatus(state);
        const busy = sending || request.kind === "waiting";
        const rows = candidate ? skuRows(candidate.tally.per_sku, names) : [];
        const quiet = runnerQuiet(state.runner_seen_at, readAt);
        const askingHere = asking?.cameraId === camera.camera_id ? asking : null;
        return (
          <div
            key={camera.camera_id}
            data-model-versions={camera.camera_id}
            className="rounded-[10px] border border-[#E5E7EB] bg-white px-4 py-3 text-[13px] leading-[1.5] text-[#374151]"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-[14px] font-semibold text-[#111827]">
                Model versions{data.length > 1 ? ` · ${camera.camera_id}` : ""}
              </h2>
              <p data-version-live>
                <span className="font-semibold text-[#111827]">Live:</span>{" "}
                <span className="font-mono text-[12px]">{state.live ?? "—"}</span>, since{" "}
                {sinceText(liveRow?.decided_at || liveRow?.created_at)}
              </p>
            </div>

            {candidate ? (
              <div data-version-candidate className="mt-2">
                <p>
                  <span className="font-semibold text-[#111827]">Candidate:</span>{" "}
                  <span className="font-mono text-[12px]">{candidate.version}</span> ·{" "}
                  {statusText(candidate.status, versions.find((v) => v.version_id === candidate.version)?.stopped_reason)} ·{" "}
                  {runLine(candidate.tally)}
                </p>
                <p data-version-verdict={candidate.verdict.state} className={`font-semibold ${VERDICT_TONE[candidate.verdict.state] ?? ""}`}>
                  {verdictText(candidate.verdict, names)}
                </p>
                {rows.length > 0 && (
                  <table className="mt-2 w-full max-w-[560px] text-left text-[12.5px]">
                    <thead className="text-[#6B7280]">
                      <tr>
                        <th className="py-1 pr-3 font-medium">Product</th>
                        <th className="py-1 pr-3 text-right font-medium">Units judged</th>
                        <th className="py-1 pr-3 text-right font-medium">Live right</th>
                        <th className="py-1 text-right font-medium">Candidate right</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.key} className="border-t border-[#F3F4F6]">
                          <td className="py-1 pr-3 text-[#111827]">{r.name}</td>
                          <td className="py-1 pr-3 text-right tabular-nums">{r.units}</td>
                          <td className="py-1 pr-3 text-right tabular-nums">{r.liveRight}</td>
                          <td className="py-1 text-right tabular-nums">{r.candRight}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ) : (
              <p data-version-candidate="none" className="mt-2 text-[#6B7280]">
                No candidate version.
              </p>
            )}

            {quiet && (
              <p data-runner-quiet className="mt-2 text-[#B91C1C]">
                The counting machine has not answered since {sinceText(state.runner_seen_at)}. A request waits
                until it is back, and is dropped if that takes more than 30 minutes.
              </p>
            )}
            {request.kind === "waiting" && !quiet && (
              <p data-version-request="waiting" className="mt-2 text-[#92400E]">
                Waiting for the counting machine…
              </p>
            )}
            {request.kind === "failed" && (
              <p data-version-request="failed" className="mt-2 text-[#B91C1C]">
                {request.message}
              </p>
            )}
            {error && <p className="mt-2 text-[#B91C1C]">{error}</p>}

            {isAdmin && !askingHere && (
              <div className="mt-3 flex flex-wrap gap-2">
                {candidate && (
                  <>
                    <button
                      type="button"
                      data-put-live
                      disabled={!canPutLive(candidate.verdict, isAdmin, busy)}
                      onClick={() =>
                        setAsking({
                          cameraId: camera.camera_id,
                          action: "put_live",
                          versionId: candidate.version,
                          question: `Put ${candidate.version} live? ${RESTART_NOTE}`,
                        })
                      }
                      className="rounded-[8px] bg-[#EE730A] px-3 py-1.5 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                    >
                      Put live
                    </button>
                    <button
                      type="button"
                      data-discard
                      disabled={busy}
                      onClick={() =>
                        setAsking({
                          cameraId: camera.camera_id,
                          action: "discard",
                          versionId: candidate.version,
                          question: `Discard ${candidate.version}? It stops running in parallel; the live version is not touched.`,
                        })
                      }
                      className="rounded-[8px] bg-[#F3F4F6] px-3 py-1.5 font-medium text-[#111827] hover:bg-[#E5E7EB] disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                    >
                      Discard
                    </button>
                  </>
                )}
                {state.previous && (
                  <button
                    type="button"
                    data-roll-back
                    disabled={busy}
                    onClick={() =>
                      setAsking({
                        cameraId: camera.camera_id,
                        action: "rollback",
                        question: `Roll back to ${state.previous}? ${RESTART_NOTE}`,
                      })
                    }
                    className="rounded-[8px] bg-[#F3F4F6] px-3 py-1.5 font-medium text-[#111827] hover:bg-[#E5E7EB] disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                  >
                    Roll back to {state.previous}
                  </button>
                )}
              </div>
            )}
            {askingHere && (
              <div data-version-confirm className="mt-3 flex flex-wrap items-center gap-2 rounded-[8px] bg-[#FFF7ED] px-3 py-2 text-[#7C2D12]">
                <p className="min-w-0 flex-1">{askingHere.question}</p>
                <button
                  type="button"
                  disabled={sending}
                  onClick={confirm}
                  className="rounded-[8px] bg-[#EE730A] px-3 py-1.5 font-semibold text-white disabled:opacity-40 cursor-pointer"
                >
                  Confirm
                </button>
                <button
                  type="button"
                  disabled={sending}
                  onClick={() => setAsking(null)}
                  className="rounded-[8px] bg-white px-3 py-1.5 font-medium text-[#111827] cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            )}

            {versions.length > 0 && (
              <details className="mt-3 text-[12.5px] text-[#6B7280]">
                <summary className="cursor-pointer select-none">History</summary>
                <ul className="mt-1 flex flex-col gap-[2px]">
                  {versions.map((v) => (
                    <li key={v.version_id}>
                      <span className="font-mono text-[12px] text-[#374151]">{v.version_id}</span> ·{" "}
                      {statusText(v.status, v.stopped_reason)} · {sinceText(v.created_at).slice(0, 5)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        );
      })}
    </section>
  );
}
