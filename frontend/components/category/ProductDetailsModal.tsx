"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, Check, ShieldCheck, X } from "lucide-react";
import {
  MILK_FLAG_THRESHOLD,
  MISMATCH_TYPE_OPTIONS,
  type SkuProduct,
} from "@/data/category-mock";

interface ProductDetailsModalProps {
  product: SkuProduct | null;
  onClose: () => void;
  onSaveAudit?: (
    productId: string,
    payload: { expectedLabel: string; mismatchType: string }
  ) => void;
}

export function ProductDetailsModal({
  product,
  onClose,
  onSaveAudit,
}: ProductDetailsModalProps) {
  const [expectedLabel, setExpectedLabel] = useState(
    () => product?.audit.expectedLabel ?? ""
  );
  const [mismatchType, setMismatchType] = useState(
    () => product?.audit.mismatchType ?? "None"
  );
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => {
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    if (product) {
      document.addEventListener("keydown", handleEsc);
    }
    return () => document.removeEventListener("keydown", handleEsc);
  }, [product, onClose]);

  if (!product) return null;

  const { cvOutput, audit } = product;
  const confidencePct = Math.round(cvOutput.confidence_score * 100);

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
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h2
                id="validation-modal-title"
                className="text-[20px] font-semibold leading-tight text-[#111827]"
              >
                Validation Card Details
              </h2>
              {cvOutput.is_flagged ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-[#FFF7ED] border border-[#FED7AA] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#C2560A]">
                  <AlertTriangle className="h-3 w-3" />
                  <span>Flagged &middot; {cvOutput.flag_reason || "Review"}</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-[#E8F5E9] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#1A932E]">
                  <Check className="h-3 w-3" strokeWidth={2.5} />
                  <span>Passed (&ge; {MILK_FLAG_THRESHOLD.toFixed(2)})</span>
                </span>
              )}
            </div>
            <p className="mt-1 text-[13px] font-normal text-[#6B7280]">
              CV Output reading{" "}
              <span className="font-mono text-[12px] text-[#374151]">
                {cvOutput.reading_id}
              </span>{" "}
              &middot; Visual pipeline ({cvOutput.pipeline})
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#111827] hover:bg-[#F3F4F6] transition-colors cursor-pointer"
          >
            <X className="h-[18px] w-[18px]" strokeWidth={2} />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-0.5">
          {/* 4 Metric Pills — strictly backed by real CV Output + Audit fields */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-[10px] bg-[#F3F4F6] px-3.5 py-2.5">
              <p className="text-[11px] font-normal text-[#6B7280]">
                Unit Count (Frame)
              </p>
              <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                {cvOutput.unit_count}{" "}
                <span className="text-[12px] font-normal text-[#6B7280]">
                  units
                </span>
              </p>
            </div>

            <div className="rounded-[10px] bg-[#F3F4F6] px-3.5 py-2.5">
              <p className="text-[11px] font-normal text-[#6B7280]">
                Confidence Score
              </p>
              <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                {cvOutput.confidence_score.toFixed(2)}{" "}
                <span className="text-[12px] font-normal text-[#6B7280]">
                  ({confidencePct}%)
                </span>
              </p>
            </div>

            <div className="rounded-[10px] bg-[#F3F4F6] px-3.5 py-2.5">
              <p className="text-[11px] font-normal text-[#6B7280]">
                CV Flag Result
              </p>
              <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                {cvOutput.is_flagged ? "Flagged" : "Pass"}
              </p>
            </div>

            <div className="rounded-[10px] bg-[#F3F4F6] px-3.5 py-2.5">
              <p className="text-[11px] font-normal text-[#6B7280]">
                Audit Status
              </p>
              <p className="mt-0.5 inline-flex items-center gap-1.5 text-[15px] font-semibold text-[#111827]">
                <span>{product.status}</span>
                {product.status === "Validated" && (
                  <Check
                    className="h-4 w-4 text-[#16A34A]"
                    strokeWidth={2.5}
                  />
                )}
              </p>
            </div>
          </div>

          {/* Section 1: Product Information (SKU Master + Alias) */}
          <div className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70 p-4">
            <h3 className="text-[13px] font-semibold text-[#111827]">
              Product Information (SKU Master)
            </h3>
            <dl className="mt-3 space-y-2.5 text-[13px]">
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">SKU Code / Alias</dt>
                <dd className="flex flex-wrap items-center gap-2 font-normal text-[#111827]">
                  <span>{product.skuCode}</span>
                  <span className="rounded bg-[#EEF0F3] px-1.5 py-0.5 font-mono text-[11px] text-[#374151]">
                    {product.modelAlias}
                  </span>
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Product Name (sku_name)</dt>
                <dd className="font-normal text-[#111827]">
                  {cvOutput.sku_name ?? "Unrecognized (null)"}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Brand / Manufacturer</dt>
                <dd className="font-normal text-[#111827]">
                  {product.brandManufacturer}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Category &amp; Pack</dt>
                <dd className="font-normal text-[#111827]">
                  {product.categoryPath} &middot; {product.packType} (
                  {product.packSize})
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Barcode</dt>
                <dd className="font-mono text-[12.5px] text-[#111827]">
                  {product.barcode}
                </dd>
              </div>
            </dl>
          </div>

          {/* Section 2: CV Detection Output (Real 16-col output, NO OCR) */}
          <div className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70 p-4">
            <h3 className="text-[13px] font-semibold text-[#111827]">
              CV Detection Output
            </h3>
            <dl className="mt-3 space-y-2.5 text-[13px]">
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Detection Method</dt>
                <dd className="font-normal text-[#111827]">
                  {cvOutput.detection_method}{" "}
                  <span className="text-[12px] text-[#6B7280]">
                    (YOLO26s &middot; DINOv2-S &middot; LanceDB)
                  </span>
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Flag Status &amp; Reason</dt>
                <dd className="font-normal text-[#111827]">
                  {cvOutput.is_flagged ? (
                    <span className="font-medium text-[#C2560A]">
                      TRUE &middot; {cvOutput.flag_reason || "Low Confidence"}
                    </span>
                  ) : (
                    <span className="font-medium text-[#1A932E]">
                      FALSE &middot; No flag
                    </span>
                  )}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">
                  Bounding Boxes ({cvOutput.bounding_box.length})
                </dt>
                <dd className="space-y-1.5">
                  <div className="flex flex-wrap gap-1.5">
                    {cvOutput.bounding_box.map((box, idx) => (
                      <span
                        key={idx}
                        className="rounded-[6px] border border-[#E5E7EB] bg-white px-2 py-0.5 font-mono text-[11px] text-[#374151]"
                      >
                        [{box.join(", ")}]
                      </span>
                    ))}
                  </div>
                  <p className="text-[11px] text-[#6B7280]">
                    Format: [x, y, width, height] in original{" "}
                    {cvOutput.frame_w}&times;{cvOutput.frame_h}px frame
                  </p>
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Processing Time</dt>
                <dd className="font-normal text-[#111827]">
                  {cvOutput.processing_time_ms} ms
                </dd>
              </div>
            </dl>
          </div>

          {/* Section 3: Human Audit & Correction (Datagent corrections / human_audit) */}
          <div className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70 p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-[13px] font-semibold text-[#111827]">
                Human Audit &amp; Correction
              </h3>
              <span className="text-[11.5px] text-[#6B7280]">
                Audit Accuracy:{" "}
                <strong className="font-semibold text-[#111827]">
                  {audit.accuracy ?? "Pending human_audit"}
                </strong>
              </span>
            </div>
            <dl className="mt-3 space-y-2.5 text-[13px]">
              <div className="grid grid-cols-1 items-center gap-1 sm:grid-cols-[200px_1fr]">
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
              <div className="grid grid-cols-1 items-center gap-1 sm:grid-cols-[200px_1fr]">
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
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Reviewed At</dt>
                <dd className="font-normal text-[#111827]">
                  {audit.reviewedAt ?? "Not yet reviewed"}
                </dd>
              </div>
            </dl>
          </div>

          {/* Section 4: Capture & S3 Traceability */}
          <div className="rounded-[12px] border border-[#E5E7EB] bg-[#F9FAFB]/70 p-4">
            <h3 className="text-[13px] font-semibold text-[#111827]">
              Capture &amp; S3 Traceability
            </h3>
            <dl className="mt-3 space-y-2.5 text-[13px]">
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Capture ID</dt>
                <dd className="font-mono text-[12px] text-[#111827]">
                  {cvOutput.capture_id}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Store / Camera / Source</dt>
                <dd className="font-normal text-[#111827]">
                  {cvOutput.store_id} &middot; {cvOutput.camera_id} &middot;{" "}
                  {cvOutput.capture_source}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">Capture Timestamp</dt>
                <dd className="font-mono text-[12px] text-[#111827]">
                  {cvOutput.capture_timestamp}
                </dd>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-[200px_1fr]">
                <dt className="text-[#6B7280]">S3 Frame Key</dt>
                <dd className="flex flex-wrap items-center gap-2">
                  <span className="break-all font-mono text-[11.5px] text-[#111827]">
                    {cvOutput.image_key}
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-[#EEF2FF] px-2 py-0.5 text-[10.5px] font-medium text-[#3730A3]">
                    <ShieldCheck className="h-3 w-3" />
                    <span>
                      Faces blurred: {cvOutput.faces_blurred}
                    </span>
                  </span>
                </dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-1">
          <p className="text-[12px] text-[#6B7280]">
            Mapped 1:1 to Datagent 16-column CV Output &amp; corrections schema.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-[8px] bg-[#F3F4F6] px-4 py-2 text-[13px] font-medium text-[#111827] hover:bg-[#E5E7EB] transition-colors cursor-pointer"
            >
              Close
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-[8px] bg-[#EE730A] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#D96504] transition-colors cursor-pointer"
            >
              {savedNotice ? "Saved ✓" : "Save Correction"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
