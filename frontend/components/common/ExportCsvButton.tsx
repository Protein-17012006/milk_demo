"use client";

import React, { useEffect, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import type { ApiExportLink } from "@/lib/api";
import {
  EXPORT_MAX_DAYS,
  defaultExportRange,
  earliestExportDay,
  exportDoneText,
  exportRangeError,
  ictDay,
  type ExportKind,
  type ExportRange,
} from "@/lib/export-ui";

interface ExportCsvButtonProps {
  kind: ExportKind;
  label: string;
  /** Classes of the opening button, so it keeps the look of the page it sits on. */
  className: string;
  /** Asks the backend to write the file; resolves to its download link. */
  request: (kind: ExportKind, range: ExportRange) => Promise<ApiExportLink>;
}

type Result = { outcome: "done" | "error"; text: string };

const DATE_INPUT =
  "mt-1 h-[34px] w-full rounded-[7px] border border-[#D1D5DB] bg-white px-2 text-[12.5px] text-[#111827] outline-none focus:border-[#EE730A]";

/** A CSV export: pick the first and last day, wait while the file is written, then the browser downloads it. */
export function ExportCsvButton({ kind, label, className, request }: ExportCsvButtonProps) {
  // openedAt: the moment the panel was opened; "today" and the oldest day on offer are read from it.
  const [openedAt, setOpenedAt] = useState<Date | null>(null);
  const [range, setRange] = useState<ExportRange | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const open = openedAt !== null;

  useEffect(() => {
    if (!open) return;
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpenedAt(null);
    }
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpenedAt(null);
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleEsc);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleEsc);
    };
  }, [open]);

  const toggle = () => {
    if (open) {
      setOpenedAt(null);
      return;
    }
    const now = new Date();
    setRange((prev) => prev ?? defaultExportRange(now));
    setResult(null);
    setOpenedAt(now);
  };

  const error = openedAt && range ? exportRangeError(range, openedAt) : null;

  const download = async () => {
    if (!range || error || busy) return;
    setBusy(true);
    setResult(null);
    try {
      const link = await request(kind, range);
      // The link carries "Content-Disposition: attachment", so the page stays where it is.
      const anchor = document.createElement("a");
      anchor.href = link.url;
      anchor.download = link.filename;
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setResult({ outcome: "done", text: exportDoneText(link.rows, range) });
    } catch {
      setResult({ outcome: "error", text: "The file could not be prepared. Try again, or choose fewer days." });
    } finally {
      setBusy(false);
    }
  };

  const setDay = (end: keyof ExportRange, value: string) => {
    setRange((prev) => (prev ? { ...prev, [end]: value } : prev));
    setResult(null);
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        data-export-open={kind}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={toggle}
        className={className}
      >
        <Download className="h-[15px] w-[15px] shrink-0" strokeWidth={1.9} />
        <span>{label}</span>
      </button>

      {openedAt && range && (
        <div
          data-export-panel
          role="dialog"
          aria-label={label}
          className="absolute right-0 top-[calc(100%+6px)] z-40 w-[272px] rounded-[10px] border border-[#E5E7EB] bg-white p-[14px] text-left shadow-[0_8px_22px_rgba(0,0,0,0.10)]"
        >
          <div className="grid grid-cols-2 gap-[10px]">
            <label className="block text-[11.5px] font-medium text-[#374151]">
              From
              <input
                type="date"
                data-export-from
                value={range.from}
                min={earliestExportDay(openedAt)}
                max={ictDay(openedAt)}
                onChange={(e) => setDay("from", e.target.value)}
                className={DATE_INPUT}
              />
            </label>
            <label className="block text-[11.5px] font-medium text-[#374151]">
              To
              <input
                type="date"
                data-export-to
                value={range.to}
                min={earliestExportDay(openedAt)}
                max={ictDay(openedAt)}
                onChange={(e) => setDay("to", e.target.value)}
                className={DATE_INPUT}
              />
            </label>
          </div>
          <p className="mt-[8px] text-[11px] leading-[1.4] text-[#6B7280]">
            Times are in UTC+7. Captures are kept for {EXPORT_MAX_DAYS} days.
          </p>

          {error && (
            <p role="alert" data-export-error className="mt-[8px] text-[11.5px] leading-[1.4] text-[#B91C1C]">
              {error}
            </p>
          )}

          <button
            type="button"
            data-export-download
            disabled={Boolean(error) || busy}
            onClick={() => void download()}
            className="mt-[10px] flex h-[34px] w-full items-center justify-center gap-[6px] rounded-[8px] bg-[#EE730A] text-[12.5px] font-semibold text-white transition-colors hover:bg-[#D96504] disabled:cursor-not-allowed disabled:opacity-55 cursor-pointer"
          >
            {busy && <Loader2 className="h-[14px] w-[14px] animate-spin" />}
            <span>{busy ? "Preparing the file…" : "Download"}</span>
          </button>

          {result && (
            <p
              role={result.outcome === "done" ? "status" : "alert"}
              data-export-result={result.outcome}
              className={`mt-[8px] text-[11.5px] leading-[1.4] ${
                result.outcome === "done" ? "text-[#166534]" : "text-[#B91C1C]"
              }`}
            >
              {result.text}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
