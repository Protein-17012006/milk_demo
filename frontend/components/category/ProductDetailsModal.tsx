"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, Check, ShieldCheck, X, ZoomIn } from "lucide-react";
import {
  MILK_FLAG_THRESHOLD,
  MISMATCH_TYPE_OPTIONS,
  auditStatusText,
  lastSeenNote,
  type SkuProduct,
} from "@/lib/products-ui";
import { focusRegion } from "@/lib/frame-geometry";
import { FrameViewer } from "./FrameViewer";

interface ProductDetailsModalProps {
  product: SkuProduct | null;
  /** The account may save corrections (field_team, team_admin); others see the reading without the form. */
  canReview: boolean;
  onClose: () => void;
  onSaveAudit?: (
    productId: string,
    payload: { expectedLabel: string; mismatchType: string }
  ) => void;
  /** Reloads GET /products/{sku} into the card; resolves to the reading id it now shows. */
  onRefreshDetail?: () => Promise<string | null>;
}

/** "2026-11-26T15:45:23+07:00" as "15:45 on 26/11", the time on the camera (UTC+7). */
const when = (ts: string) => (ts.length >= 16 ? `${ts.slice(11, 16)} on ${ts.slice(8, 10)}/${ts.slice(5, 7)}` : "—");

const ROW = "grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]";
const PILL = "rounded-[10px] bg-[#F3F4F6] px-3.5 py-2.5";

/**
 * One reading of one product. The frame with the reading's boxes comes first: it is the plainest answer to "can
 * this count be trusted". The team also gets the correction form; the fields of the CV Output row and the capture
 * (boxes as numbers, keys, ids) sit folded under "Technical details".
 */
export function ProductDetailsModal({
  product,
  canReview,
  onClose,
  onSaveAudit,
  onRefreshDetail,
}: ProductDetailsModalProps) {
  const [expectedLabel, setExpectedLabel] = useState(
    () => product?.audit.expectedLabel ?? ""
  );
  const [mismatchType, setMismatchType] = useState(
    () => product?.audit.mismatchType ?? "None"
  );
  const [savedNotice, setSavedNotice] = useState(false);
  // Frame viewer: null = closed. One link refresh per opening, then a plain error.
  const [viewer, setViewer] = useState<{ notice: string | null; retried: boolean } | null>(null);
  // The frame in the card: its real size (the zoom needs it), or that it did not load.
  const [frame, setFrame] = useState<{ url: string; w: number; h: number } | { url: string; failed: true } | null>(null);
  const frameUrl = product?.cvOutput.frame_url ?? null;

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (product) {
      document.addEventListener("keydown", handleEsc);
    }
    return () => document.removeEventListener("keydown", handleEsc);
  }, [product, onClose]);

  useEffect(() => {
    if (!frameUrl) return;
    let alive = true;
    const img = new window.Image();
    img.onload = () => {
      if (alive) setFrame({ url: frameUrl, w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => {
      if (alive) setFrame({ url: frameUrl, failed: true });
    };
    img.src = frameUrl;
    return () => {
      alive = false;
      img.onload = null;
      img.onerror = null;
    };
  }, [frameUrl]);

  if (!product) return null;

  const { cvOutput, audit } = product;
  const boxes = cvOutput.bounding_box;
  const frameAvailable = Boolean(cvOutput.frame_url) && boxes.length > 0;
  const frameReason =
    product.detailFetchedAt === null ? "Loading the frame…" : "No frame stored for this reading";
  // the frame state of the link on show (a reloaded reading brings a new link)
  const shown = frame && frame.url === frameUrl ? frame : null;
  const loaded = shown && !("failed" in shown) ? shown : null;
  const region = loaded ? focusRegion(boxes, loaded.w, loaded.h) : null;
  const labelSize = region ? region.w / 45 : 0;

  const openViewer = async () => {
    if (!frameAvailable) return;
    // Signed links live 15 minutes: reload the reading first when the card is older than 10.
    if (onRefreshDetail && Date.now() - (product.detailFetchedAt ?? 0) > 600_000) {
      await onRefreshDetail();
    }
    setViewer({ notice: null, retried: false });
  };

  const handleFrameError = async () => {
    if (!viewer) return;
    if (viewer.retried || !onRefreshDetail) {
      setViewer({ ...viewer, notice: "Frame could not be loaded." });
      return;
    }
    const before = cvOutput.reading_id;
    setViewer({ notice: null, retried: true });
    const now = await onRefreshDetail();
    // A failed reload keeps the dead link: say so plainly instead of claiming a reload.
    setViewer((v) =>
      v && {
        ...v,
        notice:
          now === null
            ? "Frame could not be loaded."
            : "The signed link expired, so the card reloaded the latest reading." +
              (now !== before ? ` It is now ${now}.` : ""),
      }
    );
  };
  const confidencePct = Math.round(cvOutput.confidence_score * 100);
  const auditStatus = auditStatusText(product.status, audit.reviewedAt);
  const lastSeen = lastSeenNote(cvOutput.unit_count, boxes.length, cvOutput.capture_timestamp);

  const handleSave = () => {
    onSaveAudit?.(product.id, { expectedLabel, mismatchType });
    setSavedNotice(true);
    setTimeout(() => {
      setSavedNotice(false);
      onClose();
    }, 550);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="validation-modal-title"
    >
      <div
        className="flex max-h-[90vh] w-full max-w-[820px] flex-col overflow-hidden rounded-[14px] border border-[#E5E7EB] bg-white p-[20px] shadow-[0_4px_24px_rgba(0,0,0,0.12)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2
                id="validation-modal-title"
                className="text-[20px] font-semibold leading-tight text-[#111827]"
              >
                {canReview ? "Validation Card Details" : "Product details"}
              </h2>
              {canReview &&
                (cvOutput.is_flagged ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#FFF7ED] border border-[#FED7AA] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#C2560A]">
                    <AlertTriangle className="h-3 w-3" />
                    <span>Flagged &middot; {cvOutput.flag_reason || "Review"}</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#E8F5E9] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#1A932E]">
                    <Check className="h-3 w-3" strokeWidth={2.5} />
                    <span>Passed (&ge; {MILK_FLAG_THRESHOLD.toFixed(2)})</span>
                  </span>
                ))}
            </div>
            <p className="mt-1 text-[13px] font-normal text-[#6B7280]">
              {canReview ? (
                <>
                  CV Output reading{" "}
                  <span className="font-mono text-[12px] text-[#374151]">{cvOutput.reading_id}</span>
                </>
              ) : (
                (cvOutput.sku_name ?? product.name)
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[#111827] hover:bg-[#F3F4F6] transition-colors cursor-pointer"
          >
            <X className="h-[18px] w-[18px]" strokeWidth={2} />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-0.5">
          {/* The numbers: a viewer needs the count and when it was read; the team also the model's own numbers */}
          <div className={`grid grid-cols-2 gap-3 ${canReview ? "sm:grid-cols-4" : ""}`}>
            <div className={PILL}>
              <p className="text-[11px] font-normal text-[#6B7280]">{canReview ? "Unit Count (Frame)" : "Units"}</p>
              <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                {cvOutput.unit_count}{" "}
                <span className="text-[12px] font-normal text-[#6B7280]">
                  {cvOutput.unit_count === 1 ? "unit" : "units"}
                </span>
              </p>
            </div>

            {!canReview && (
              <div className={PILL}>
                <p className="text-[11px] font-normal text-[#6B7280]">Read at</p>
                <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">{when(cvOutput.capture_timestamp)}</p>
              </div>
            )}

            {canReview && (
              <>
                <div className={PILL}>
                  <p className="text-[11px] font-normal text-[#6B7280]">Confidence Score</p>
                  <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                    {cvOutput.confidence_score.toFixed(2)}{" "}
                    <span className="text-[12px] font-normal text-[#6B7280]">({confidencePct}%)</span>
                  </p>
                </div>

                <div className={PILL}>
                  <p className="text-[11px] font-normal text-[#6B7280]">CV Flag Result</p>
                  <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                    {cvOutput.is_flagged ? "Flagged" : "Pass"}
                  </p>
                </div>

                <div className={PILL}>
                  <p className="text-[11px] font-normal text-[#6B7280]">Audit Status</p>
                  <p className="mt-0.5 inline-flex items-center gap-1.5 text-[15px] font-semibold text-[#111827]">
                    <span>{auditStatus}</span>
                    {auditStatus === "Validated" && (
                      <Check className="h-4 w-4 text-[#16A34A]" strokeWidth={2.5} />
                    )}
                  </p>
                </div>
              </>
            )}
          </div>
          {product.reviewQueueKey && (
            <p
              data-from-queue
              role="status"
              className="rounded-[10px] border border-[#FED7AA] bg-[#FFF7ED] px-3.5 py-2 text-[12.5px] leading-[1.45] text-[#7C2D12]"
            >
              From the review queue: this is the doubtful reading of {cvOutput.capture_timestamp.slice(11, 16)} on{" "}
              {cvOutput.capture_timestamp.slice(8, 10)}/{cvOutput.capture_timestamp.slice(5, 7)}, not the
              product&apos;s latest one. Saving a correction checks it off.
            </p>
          )}
          {lastSeen && (
            <p
              data-last-seen
              role="status"
              className="rounded-[10px] border border-[#FDE68A] bg-[#FFFBEB] px-3.5 py-2 text-[12.5px] leading-[1.45] text-[#92400E]"
            >
              {lastSeen}
            </p>
          )}

          {/* The frame of this reading, zoomed on the product, with its boxes numbered */}
          <div data-card-frame className="overflow-hidden rounded-[12px] border border-[#E5E7EB]">
            {frameAvailable && loaded && region ? (
              <button
                type="button"
                data-card-frame-open
                title="Open the frame large"
                onClick={() => void openViewer()}
                className="relative block w-full cursor-zoom-in bg-[#111827]"
              >
                <svg
                  viewBox={`${region.x} ${region.y} ${region.w} ${region.h}`}
                  preserveAspectRatio="xMidYMid meet"
                  className="block max-h-[300px] w-full"
                  role="img"
                  aria-label={`Frame with ${boxes.length} boxes`}
                >
                  <image href={loaded.url} x={0} y={0} width={loaded.w} height={loaded.h} />
                  {boxes.map(([x, y, w, h], i) => (
                    <g key={`${i}-${x}-${y}`}>
                      <rect
                        data-box
                        x={x}
                        y={y}
                        width={w}
                        height={h}
                        fill="none"
                        stroke="#FF4000"
                        strokeWidth={2}
                        vectorEffect="non-scaling-stroke"
                      />
                      <text
                        x={x}
                        y={Math.max(y - labelSize * 0.3, labelSize)}
                        fontSize={labelSize}
                        fontWeight={700}
                        fill="#FF4000"
                        stroke="#FFFFFF"
                        strokeWidth={labelSize / 6}
                        paintOrder="stroke"
                      >
                        {i + 1}
                      </text>
                    </g>
                  ))}
                </svg>
                <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-[6px] bg-black/60 px-2 py-1 text-[11px] font-medium text-white">
                  <ZoomIn className="h-3.5 w-3.5" />
                  Open large
                </span>
              </button>
            ) : (
              <p data-card-frame-message className="bg-[#F9FAFB] px-4 py-8 text-center text-[12.5px] text-[#6B7280]">
                {!frameAvailable
                  ? frameReason
                  : shown && "failed" in shown
                    ? "The frame could not be loaded."
                    : "Loading the frame…"}
              </p>
            )}
            {frameAvailable && (
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[#E5E7EB] bg-white px-3.5 py-2 text-[12px] text-[#6B7280]">
                <span>
                  {boxes.length} {boxes.length === 1 ? "box" : "boxes"} in the frame of {when(cvOutput.capture_timestamp)}
                </span>
                {cvOutput.faces_blurred > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#EEF2FF] px-2 py-0.5 text-[10.5px] font-medium text-[#3730A3]">
                    <ShieldCheck className="h-3 w-3" />
                    Faces blurred: {cvOutput.faces_blurred}
                  </span>
                )}
              </p>
            )}
          </div>

          {/* The product, from the SKU master */}
          <div className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70 p-4">
            <h3 className="text-[13px] font-semibold text-[#111827]">Product</h3>
            <dl className="mt-3 space-y-2.5 text-[13px]">
              <div className={ROW}>
                <dt className="text-[#6B7280]">Product name</dt>
                <dd className="font-normal text-[#111827]">{cvOutput.sku_name ?? "Unrecognized"}</dd>
              </div>
              <div className={ROW}>
                <dt className="text-[#6B7280]">Brand / Manufacturer</dt>
                <dd className="font-normal text-[#111827]">{product.brandManufacturer}</dd>
              </div>
              <div className={ROW}>
                <dt className="text-[#6B7280]">Category &amp; Pack</dt>
                <dd className="font-normal text-[#111827]">
                  {product.categoryPath} &middot; {product.packType} ({product.packSize})
                </dd>
              </div>
              {canReview && (
                <>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">SKU Code / Alias</dt>
                    <dd className="flex flex-wrap items-center gap-2 font-normal text-[#111827]">
                      <span>{product.skuCode}</span>
                      <span className="rounded bg-[#EEF0F3] px-1.5 py-0.5 font-mono text-[11px] text-[#374151]">
                        {product.modelAlias}
                      </span>
                    </dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Barcode</dt>
                    <dd className="font-mono text-[12.5px] text-[#111827]">{product.barcode}</dd>
                  </div>
                </>
              )}
            </dl>
          </div>

          {/* Human Audit & Correction (the team only) */}
          {canReview && (
            <div className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70 p-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-[13px] font-semibold text-[#111827]">Human Audit &amp; Correction</h3>
                <span className="text-[11.5px] text-[#6B7280]">
                  Audit Accuracy:{" "}
                  <strong className="font-semibold text-[#111827]">{audit.accuracy ?? "Not audited yet"}</strong>
                </span>
              </div>
              <dl className="mt-3 space-y-2.5 text-[13px]">
                <div className={`${ROW} items-center`}>
                  <dt className="text-[#6B7280]">Expected Label</dt>
                  <dd>
                    <input
                      type="text"
                      aria-label="Expected Label"
                      value={expectedLabel}
                      onChange={(e) => setExpectedLabel(e.target.value)}
                      className="h-[34px] w-full rounded-[7px] border border-[#D1D5DB] bg-white px-2.5 text-[12.5px] text-[#111827] outline-none focus:border-[#EE730A]"
                    />
                  </dd>
                </div>
                <div className={`${ROW} items-center`}>
                  <dt className="text-[#6B7280]">Mismatch Type</dt>
                  <dd>
                    <select
                      aria-label="Mismatch Type"
                      value={mismatchType}
                      onChange={(e) => setMismatchType(e.target.value)}
                      className="h-[34px] w-full rounded-[7px] border border-[#D1D5DB] bg-white px-2.5 text-[12.5px] text-[#111827] outline-none focus:border-[#EE730A]"
                    >
                      {MISMATCH_TYPE_OPTIONS.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  </dd>
                </div>
                <div className={ROW}>
                  <dt className="text-[#6B7280]">Reviewed At</dt>
                  <dd className="font-normal text-[#111827]">{audit.reviewedAt ?? "Not yet reviewed"}</dd>
                </div>
              </dl>
            </div>
          )}

          {/* The fields of the CV Output row and of the capture: for tracing a reading, closed until asked for */}
          <details data-technical className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70">
            <summary className="cursor-pointer select-none px-4 py-3 text-[13px] font-semibold text-[#111827]">
              Technical details
            </summary>
            <div className="space-y-4 border-t border-[#E5E7EB] px-4 py-4">
              <div>
                <h3 className="text-[12.5px] font-semibold text-[#374151]">CV Detection Output</h3>
                <dl className="mt-2.5 space-y-2.5 text-[13px]">
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Detection Method</dt>
                    <dd className="font-normal text-[#111827]">{cvOutput.detection_method}</dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Flag Status &amp; Reason</dt>
                    <dd className="font-normal text-[#111827]">
                      {cvOutput.is_flagged ? (
                        <span className="font-medium text-[#C2560A]">
                          Flagged &middot; {cvOutput.flag_reason || "Low Confidence"}
                        </span>
                      ) : (
                        <span className="font-medium text-[#1A932E]">Not flagged</span>
                      )}
                    </dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Bounding Boxes ({boxes.length})</dt>
                    <dd className="space-y-1.5">
                      <div className="flex flex-wrap gap-1.5">
                        {boxes.map((box, idx) => (
                          <span
                            key={idx}
                            className="rounded-[6px] border border-[#E5E7EB] bg-white px-2 py-0.5 font-mono text-[11px] text-[#374151]"
                          >
                            [{box.join(", ")}]
                          </span>
                        ))}
                      </div>
                      <p className="text-[11px] text-[#6B7280]">
                        Format: [x, y, width, height] in original {cvOutput.frame_w}&times;{cvOutput.frame_h}px frame
                      </p>
                    </dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Processing Time</dt>
                    <dd className="font-normal text-[#111827]">
                      {/* a reading opened from the review queue does not carry its processing time */}
                      {cvOutput.processing_time_ms > 0 ? `${cvOutput.processing_time_ms} ms` : "—"}
                    </dd>
                  </div>
                </dl>
              </div>

              <div>
                <h3 className="text-[12.5px] font-semibold text-[#374151]">Capture</h3>
                <dl className="mt-2.5 space-y-2.5 text-[13px]">
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Reading ID</dt>
                    <dd className="font-mono text-[12px] text-[#111827]">{cvOutput.reading_id}</dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Capture ID</dt>
                    <dd className="font-mono text-[12px] text-[#111827]">{cvOutput.capture_id}</dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Store / Camera / Source</dt>
                    <dd className="font-normal text-[#111827]">
                      {cvOutput.store_id} &middot; {cvOutput.camera_id} &middot; {cvOutput.capture_source}
                    </dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Capture Timestamp</dt>
                    <dd className="font-mono text-[12px] text-[#111827]">{cvOutput.capture_timestamp}</dd>
                  </div>
                  <div className={ROW}>
                    <dt className="text-[#6B7280]">Frame file</dt>
                    <dd className="break-all font-mono text-[11.5px] text-[#111827]">{cvOutput.image_key}</dd>
                  </div>
                </dl>
              </div>
            </div>
          </details>
        </div>

        {/* Footer */}
        <div className="mt-4 flex flex-wrap items-center justify-end gap-3 pt-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-[8px] bg-[#F3F4F6] px-4 py-2 text-[13px] font-medium text-[#111827] hover:bg-[#E5E7EB] transition-colors cursor-pointer"
            >
              Close
            </button>
            {canReview && (
              <button
                type="button"
                onClick={handleSave}
                className="rounded-[8px] bg-[#EE730A] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#D96504] transition-colors cursor-pointer"
              >
                {savedNotice ? "Saved ✓" : "Save Correction"}
              </button>
            )}
          </div>
        </div>
      </div>
      {viewer && cvOutput.frame_url && (
        <FrameViewer
          url={cvOutput.frame_url}
          boxes={boxes}
          readingId={cvOutput.reading_id}
          captureTimestamp={cvOutput.capture_timestamp}
          unitCount={cvOutput.unit_count}
          confidence={cvOutput.confidence_score}
          facesBlurred={cvOutput.faces_blurred}
          notice={viewer.notice}
          onImageError={() => void handleFrameError()}
          onClose={() => setViewer(null)}
        />
      )}
    </div>
  );
}
