"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, ShieldCheck, X, ZoomIn } from "lucide-react";
import type { ApiShelfFrame } from "@/lib/api";
import { focusRegion } from "@/lib/frame-geometry";
import { frameLegend } from "@/lib/shelf-now";

interface ShelfFrameViewerProps {
  /** The newest capture of a camera, with a signed link to its frame (the caller opens the viewer only with one). */
  frame: ApiShelfFrame;
  onClose(): void;
  /** The frame did not load (the link expired, or the image is gone). */
  onImageError(): void;
}

/** "2026-11-26T15:45:23+07:00" as "15:45 on 26/11", the time on the camera (UTC+7). */
const when = (ts: string | null) =>
  ts && ts.length >= 16 ? `${ts.slice(11, 16)} on ${ts.slice(8, 10)}/${ts.slice(5, 7)}` : "";

/**
 * The shelf photo the numbers were read from, with every product's boxes drawn in that product's colour (SVG over
 * the image, so nothing is re-encoded and the signed link stays in the browser). Opens zoomed on the boxes.
 */
export function ShelfFrameViewer({ frame, onClose, onImageError }: ShelfFrameViewerProps) {
  const url = frame.frame_presigned_url ?? "";
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [zoomed, setZoomed] = useState(true);
  const onErrorRef = useRef(onImageError);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onErrorRef.current = onImageError;
    onCloseRef.current = onClose;
  });

  // Learn the frame's real size from the image itself (the SVG needs it); a failed load goes back to the page.
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onCloseRef.current();
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, []);

  const legend = useMemo(() => frameLegend(frame.products), [frame.products]);
  const allBoxes = useMemo(() => legend.flatMap((item) => item.boxes), [legend]);
  const region = useMemo(() => {
    if (!size) return null;
    return zoomed ? focusRegion(allBoxes, size.w, size.h) : { x: 0, y: 0, w: size.w, h: size.h };
  }, [size, zoomed, allBoxes]);

  return createPortal(
    <div
      data-shelf-frame-viewer
      role="dialog"
      aria-modal="true"
      aria-label="Shelf photo"
      className="fixed inset-0 z-[60] flex flex-col bg-black/80"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#111827] px-5 py-3 text-white">
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px]">
          <span className="font-semibold">Shelf photo</span>
          <span className="text-white/70">{when(frame.capture_timestamp)}</span>
          <span>
            {allBoxes.length} {allBoxes.length === 1 ? "box" : "boxes"}
          </span>
          {frame.faces_blurred > 0 && (
            <span className="inline-flex items-center gap-1 text-white/80">
              <ShieldCheck className="h-3.5 w-3.5" />
              Faces blurred: {frame.faces_blurred}
            </span>
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
            aria-label="Close shelf photo"
            className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-white/10 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Which colour is which product, and how many of it the reading counted in this frame */}
      <ul data-frame-legend className="flex flex-wrap gap-x-4 gap-y-1 bg-[#1F2937] px-5 py-2 text-[12px] text-white">
        {legend.length === 0 && <li className="text-white/70">No product was counted in this frame.</li>}
        {legend.map((item) => (
          <li key={item.name} className="inline-flex items-center gap-1.5">
            <span className="h-[10px] w-[10px] shrink-0 rounded-[2px]" style={{ backgroundColor: item.color }} />
            <span>
              {item.name} × {item.count}
            </span>
          </li>
        ))}
        {legend.length > 0 && (
          <li data-frame-note className="basis-full text-[11.5px] text-white/60">
            Boxes are the ones in this photo. The numbers on the page are steadied over the last three readings, so one
            can differ from the photo by a unit.
          </li>
        )}
      </ul>

      <div className="flex min-h-0 flex-1 items-center justify-center p-4">
        {region && size ? (
          <svg
            viewBox={`${region.x} ${region.y} ${region.w} ${region.h}`}
            preserveAspectRatio="xMidYMid meet"
            className="h-full w-full"
            role="img"
            aria-label={`Shelf photo with ${allBoxes.length} boxes`}
          >
            <image href={url} x={0} y={0} width={size.w} height={size.h} />
            {legend.map((item) =>
              item.boxes.map(([x, y, w, h], i) => (
                <rect
                  key={`${item.name}-${i}-${x}-${y}`}
                  data-box
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  fill="none"
                  stroke={item.color}
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              ))
            )}
          </svg>
        ) : (
          <p className="text-[13px] text-white/70">Loading the photo…</p>
        )}
      </div>
    </div>,
    document.body
  );
}
