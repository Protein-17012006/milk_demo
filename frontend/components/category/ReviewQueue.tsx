"use client";

import React from "react";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import type { ApiReviewQueueItem } from "@/lib/api";
import { isWaiting, orderForReview, reviewSummary } from "@/lib/review-queue";

const REASON: Record<string, string> = { "Low Confidence": "Low confidence", Unrecognized: "No SKU matched" };
const STATUS: Record<string, string> = { "Chờ duyệt": "Waiting", "Đã xác nhận": "Confirmed", "Đã sửa": "Corrected" };

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "2026-11-23T22:00:22+07:00" as "23/11 22:00", the time on the camera (UTC+7). */
const when = (ts?: string | null) =>
  ts && ts.length >= 16 ? `${ts.slice(8, 10)}/${ts.slice(5, 7)} ${ts.slice(11, 16)}` : "—";

interface ReviewBannerProps {
  items: ApiReviewQueueItem[];
  unrecognizedUnits: number | null;
  onOpen: () => void;
}

/** Above the product list: how many doubtful readings wait for a person, and what that person does with them. */
export function ReviewBanner({ items, unrecognizedUnits, onOpen }: ReviewBannerProps) {
  const s = reviewSummary(items);
  const unmatched =
    unrecognizedUnits && unrecognizedUnits > 0
      ? ` ${plural(unrecognizedUnits, "unit", "units")} on the shelf matched no SKU, so ${unrecognizedUnits === 1 ? "it is" : "they are"} not in the list below.`
      : "";

  if (s.waiting === 0) {
    return (
      <div
        data-review-banner="clear"
        className="mt-[16px] flex flex-col gap-2 rounded-[10px] border border-[#E5E7EB] bg-white py-[10px] pl-[14px] pr-[16px] sm:flex-row sm:items-center sm:justify-between sm:gap-6"
      >
        <div className="flex min-w-0 flex-1 items-start gap-[10px]">
          <CheckCircle2 className="mt-[2px] h-[16px] w-[16px] shrink-0 text-[#15803D]" strokeWidth={1.9} />
          <p className="text-[13px] leading-[1.5] text-[#374151]">
            <span className="font-semibold text-[#111827]">Nothing to review.</span> When the model is unsure about a
            reading (confidence under 0.70, or no SKU matched), it waits in the review queue until a person confirms or
            corrects it.{unmatched}
          </p>
        </div>
        <button
          type="button"
          onClick={onOpen}
          className="shrink-0 text-[13px] font-semibold text-[#374151] hover:underline cursor-pointer"
        >
          Open review queue
        </button>
      </div>
    );
  }

  const reasons = [
    s.waitingLowConfidence > 0 ? `${s.waitingLowConfidence} with confidence under 0.70` : "",
    s.waitingUnrecognized > 0 ? `${s.waitingUnrecognized} that matched no SKU` : "",
  ]
    .filter(Boolean)
    .join(" and ");
  return (
    <div
      data-review-banner="waiting"
      className="mt-[16px] flex flex-col gap-2 rounded-[10px] border border-[#FED7AA] bg-[#FFF7ED] py-[10px] pl-[14px] pr-[16px] sm:flex-row sm:items-center sm:justify-between sm:gap-6"
    >
      <div className="flex min-w-0 flex-1 items-start gap-[10px]">
        <AlertTriangle className="mt-[2px] h-[16px] w-[16px] shrink-0 text-[#C2560A]" strokeWidth={1.9} />
        <p className="text-[13px] leading-[1.5] text-[#7C2D12]">
          <span className="font-semibold">{plural(s.waiting, "reading is", "readings are")} waiting for a check.</span>{" "}
          The model was unsure about {s.waiting === 1 ? "it" : "them"}
          {reasons ? `: ${reasons}` : ""}. Look at each frame, then confirm the AI&apos;s reading or correct it in the
          product&apos;s card (View on its row).{unmatched}
        </p>
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="shrink-0 rounded-[8px] bg-[#EE730A] px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-[#D96504] cursor-pointer"
      >
        Review readings
      </button>
    </div>
  );
}

interface ReviewQueueDialogProps {
  items: ApiReviewQueueItem[];
  onClose: () => void;
  onConfirm: (item: ApiReviewQueueItem) => void;
}

/** The review queue: readings still waiting for a person first, then the ones already checked. */
export function ReviewQueueDialog({ items, onClose, onConfirm }: ReviewQueueDialogProps) {
  const ordered = orderForReview(items);
  const waiting = ordered.filter((i) => isWaiting(i.status));
  const checked = ordered.filter((i) => !isWaiting(i.status));
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-queue-title"
        className="w-full max-w-[680px] overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white shadow-[0_10px_28px_rgba(0,0,0,0.14)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#EFF0F6] px-5 py-4">
          <div>
            <h3 id="review-queue-title" className="text-[16px] font-semibold text-[#111827]">
              Review queue
            </h3>
            <p className="mt-1 max-w-[78ch] text-[12.5px] leading-[1.5] text-[#6B7280]">
              Readings the model was unsure about: confidence under 0.70, or boxes that matched no SKU. Open the frame.
              If the reading is right, confirm it; if it is wrong, correct it in the product&apos;s card (View on its
              row). Each camera, SKU and reason keeps one item, and a new doubtful reading sets it back to waiting.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close review queue"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827] cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto px-5 py-2">
          <QueueGroup title={`Waiting for a check (${waiting.length})`} empty="Nothing is waiting." items={waiting} onConfirm={onConfirm} />
          <QueueGroup title={`Checked (${checked.length})`} empty="Nothing has been checked yet." items={checked} />
        </div>
        <div className="flex justify-end border-t border-[#EFF0F6] px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-[8px] bg-[#F3F4F6] px-4 py-1.5 text-[13px] font-medium text-[#111827] hover:bg-[#E5E7EB] cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function QueueGroup({
  title,
  empty,
  items,
  onConfirm,
}: {
  title: string;
  empty: string;
  items: ApiReviewQueueItem[];
  onConfirm?: (item: ApiReviewQueueItem) => void;
}) {
  return (
    <section className="py-2">
      <h4 className="text-[12.5px] font-semibold text-[#374151]">{title}</h4>
      {items.length === 0 ? (
        <p className="py-3 text-[12.5px] text-[#6B7280]">{empty}</p>
      ) : (
        <ul className="divide-y divide-[#EFF0F6]">
          {items.map((det) => (
            <QueueItem key={det.queue_key} det={det} onConfirm={onConfirm} />
          ))}
        </ul>
      )}
    </section>
  );
}

function QueueItem({ det, onConfirm }: { det: ApiReviewQueueItem; onConfirm?: (item: ApiReviewQueueItem) => void }) {
  const waiting = isWaiting(det.status);
  return (
    <li
      data-queue-item
      data-queue-status={waiting ? "waiting" : "checked"}
      className="flex flex-wrap items-center justify-between gap-4 py-3"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-[#FFF7ED] px-2 py-0.5 text-[11px] font-semibold text-[#C2560A]">
            {REASON[det.flag_reason] ?? det.flag_reason}
          </span>
          <span className="rounded-full bg-[#F3F4F6] px-2 py-0.5 text-[11px] font-medium text-[#374151]">
            {STATUS[det.status] ? `${STATUS[det.status]} (${det.status})` : det.status}
          </span>
        </div>
        <p className="mt-1 truncate text-[13px] font-medium text-[#111827]">
          {det.sku_name || det.sku_id}: {plural(Number(det.unit_count), "unit", "units")} at confidence{" "}
          {Number(det.confidence_score).toFixed(2)}
        </p>
        <p className="mt-0.5 text-[11.5px] text-[#6B7280]">
          {det.camera_id}, {when(det.capture_timestamp)}
          {!waiting && det.reviewed_by ? `. Checked by ${det.reviewed_by} on ${when(det.reviewed_at)}` : ""}
          {det.frame_presigned_url && (
            <>
              {". "}
              <a
                href={det.frame_presigned_url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-[#0051C3] hover:underline"
              >
                Open frame
              </a>{" "}
              (link valid 15 min)
            </>
          )}
        </p>
      </div>
      {waiting && onConfirm && (
        <button
          type="button"
          onClick={() => onConfirm(det)}
          className="shrink-0 rounded-[6px] border border-[#E5E7EB] px-2.5 py-1 text-[12px] font-medium text-[#111827] hover:bg-[#F9FAFB] cursor-pointer"
        >
          Confirm AI
        </button>
      )}
    </li>
  );
}
