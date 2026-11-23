"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, ShieldCheck, X, ZoomIn } from "lucide-react";
import { focusRegion, type Box } from "@/lib/frame-geometry";

interface FrameViewerProps {
  /** Signed S3 link to the face-blurred frame (15 min); never logged. */
  url: string;
  boxes: Box[];
  readingId: string;
  captureTimestamp: string;
  unitCount: number;
  confidence: number;
  facesBlurred: number;
  notice: string | null;
  onImageError(): void;
  onClose(): void;
}

/**
 * Full-screen view of the stored frame with the reading's boxes drawn on it (SVG over the image, so no
 * image is re-encoded and the signed link stays in the browser). Opens zoomed on the boxes.
 */
export function FrameViewer({
  url,
  boxes,
  readingId,
  captureTimestamp,
  unitCount,
  confidence,
  facesBlurred,
  notice,
  onImageError,
  onClose,
}: FrameViewerProps) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [zoomed, setZoomed] = useState(true);
  const onErrorRef = useRef(onImageError);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onErrorRef.current = onImageError;
    onCloseRef.current = onClose;
  });

  // Learn the frame's real size from the image itself (the SVG needs it); a failed load goes to the card.
  useEffect(() => {
    let alive = true;
    const img = new window.Image();
    img.onload = () => {
      if (alive) setSize({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => {
      if (alive) onErrorRef.current();
    };
    img.src = url;
    return () => {
      alive = false;
      img.onload = null;
      img.onerror = null;
    };
  }, [url]);

  // Escape closes only the viewer: caught on window before it reaches the card's listener on document.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onCloseRef.current();
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, []);

  const region = useMemo(() => {
    if (!size) return null;
    return zoomed ? focusRegion(boxes, size.w, size.h) : { x: 0, y: 0, w: size.w, h: size.h };
  }, [size, zoomed, boxes]);
  const label = region ? region.w / 45 : 0;

  return createPortal(
    <div
      data-frame-viewer
      role="dialog"
      aria-modal="true"
      aria-label={`Frame of reading ${readingId}`}
      className="fixed inset-0 z-[60] flex flex-col bg-black/80"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#111827] px-5 py-3 text-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
          <span className="font-mono text-[12px]">{readingId}</span>
          <span className="text-white/70">{captureTimestamp}</span>
          <span>
            {unitCount} {unitCount === 1 ? "unit" : "units"} · {boxes.length}{" "}
            {boxes.length === 1 ? "box" : "boxes"}
          </span>
          <span>Confidence {confidence.toFixed(2)}</span>
          <span className="inline-flex items-center gap-1 text-white/80">
            <ShieldCheck className="h-3.5 w-3.5" />
            Faces blurred: {facesBlurred}
          </span>
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
            aria-label="Close frame"
            className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-white/10 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {notice && (
        <p data-frame-notice className="bg-[#FFF7ED] px-5 py-2 text-[12.5px] text-[#7C2D12]">
          {notice}
        </p>
      )}

      <div className="flex min-h-0 flex-1 items-center justify-center p-4">
        {region && size ? (
          <svg
            viewBox={`${region.x} ${region.y} ${region.w} ${region.h}`}
            preserveAspectRatio="xMidYMid meet"
            className="h-full w-full"
            role="img"
            aria-label={`Frame with ${boxes.length} boxes`}
          >
            <image href={url} x={0} y={0} width={size.w} height={size.h} />
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
                  y={Math.max(y - label * 0.3, label)}
                  fontSize={label}
                  fontWeight={700}
                  fill="#FF4000"
                  stroke="#FFFFFF"
                  strokeWidth={label / 6}
                  paintOrder="stroke"
                >
                  {i + 1}
                </text>
              </g>
            ))}
          </svg>
        ) : (
          <p className="text-[13px] text-white/70">Loading frame…</p>
        )}
      </div>
    </div>,
    document.body
  );
}
