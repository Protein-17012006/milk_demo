"use client";

import React, { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import type { ApiEventPhotos, ApiShelfEvent, ApiShelfEventsResponse, ShelfEventType, ShelfVerdict } from "@/lib/api";
import { focusRegion, type Box } from "@/lib/frame-geometry";
import { BADGE_COLORS, badgePillText } from "@/lib/reliability-ui";
import { earlierText, eventLabel, eventText, foldEvents, gapText, oosDurationText, timeAgo, type EventFold } from "@/lib/shelf-ui";

export type ActivityKind = "all" | "alerts" | "restocked";

interface RecentActivitiesCardProps {
  /** Loads one page of events for the Dashboard filters; null while signed out. */
  load: ((kind: ActivityKind, cursor?: string) => Promise<ApiShelfEventsResponse>) | null;
  /** Changes whenever the Dashboard filters change, so the card loads again. */
  reloadKey: string;
  /** Shown instead of an empty list when the shelf numbers are blocked (for example, no opening hours). */
  blockedText: string | null;
  /** "Alerts confirmed right: 7 of 10", from the Dashboard's /kpi call; null when there is none. */
  accuracyLine: string | null;
  /** "OOS 7 of 9 · Restocked 3 of 4": the same number per kind of event; null when none is confirmed yet. */
  accuracyByType: string | null;
  /** Only team_admin and field_team confirm events; datagent only looks. */
  canVerify: boolean;
  loadPhotos: ((storeId: string, eventKey: string) => Promise<ApiEventPhotos>) | null;
  saveVerdict: ((storeId: string, eventKey: string, verdict: ShelfVerdict) => Promise<unknown>) | null;
  /** Told the first page of the "All" filter when it arrives (and whether older events exist), for the team's
   * count of events still to confirm. */
  onFirstPage?: (items: ApiShelfEvent[], hasMore: boolean) => void;
}

const VERDICTS: { id: ShelfVerdict; label: string; active: string }[] = [
  { id: "right", label: "Right", active: "border-[#2E7D32] bg-[#E8F5E9] text-[#2E7D32]" },
  { id: "wrong", label: "Wrong", active: "border-[#DC2626] bg-[#FEE2E2] text-[#DC2626]" },
  { id: "unsure", label: "Unsure", active: "border-[#6B7280] bg-[#F3F4F6] text-[#374151]" },
];

const BADGE_STYLES: Record<ShelfEventType, string> = {
  OOS: "bg-[#FEE2E2] text-[#DC2626]",
  RESTOCKED: "bg-[#E8F5E9] text-[#2E7D32]",
  DEPLETED: "bg-[#FFF3E0] text-[#E65100]",
  LOW_STOCK: "bg-[#FEF3C7] text-[#D97706]",
};

const FILTER_OPTIONS: { id: ActivityKind; label: string }[] = [
  { id: "all", label: "All" },
  { id: "alerts", label: "Alerts Only" },
  { id: "restocked", label: "Restocked" },
];

interface RowActions {
  canVerify: boolean;
  verdictOf: (item: ApiShelfEvent) => ShelfVerdict | undefined;
  onVerdict: (item: ApiShelfEvent, verdict: ShelfVerdict) => void;
  onPhotos: (item: ApiShelfEvent) => void;
}

function EventRow({ item, now, actions }: { item: ApiShelfEvent; now: Date; actions: RowActions }) {
  const gap = gapText(item);
  const chosen = actions.verdictOf(item);
  return (
    <article data-shelf-event={item.type} className="flex flex-col gap-[4px] py-[9px]">
      <div className="flex items-center gap-[8px]">
        <span className={`shrink-0 rounded-full px-[10px] py-[2px] text-[11px] font-semibold leading-tight ${BADGE_STYLES[item.type]}`}>
          {eventLabel(item.type)}
        </span>
        <h3 className="truncate text-[13px] font-semibold leading-[18px] text-[#111827]">{item.sku_name}</h3>
      </div>
      {/* the reliability pill sits under the name: beside it, it squeezed the name down to a few letters */}
      <div className="flex flex-wrap items-center gap-[8px]">
        <span className="text-[12px] leading-[16px] text-[#9CA3AF]">{timeAgo(item.at, now)}</span>
        {item.badge && (
          <span
            data-reliability={item.badge}
            title="Reliability of this SKU, from the labelled frames of the last 14 days"
            className={`shrink-0 rounded-full px-[8px] py-[1px] text-[10.5px] font-semibold leading-tight ${BADGE_COLORS[item.badge]}`}
          >
            {badgePillText(item.badge)}
          </span>
        )}
      </div>
      <span className="text-[12px] leading-[16px] text-[#6B7280]">{item.store_name}</span>
      <span className="text-[12px] font-medium leading-[16px] text-[#374151]">
        {eventText(item)}
        {oosDurationText(item)}
      </span>
      {gap && (
        <span data-shelf-event-gap className="text-[12px] leading-[16px] text-[#9CA3AF]">
          {gap}
        </span>
      )}
      <div className="mt-[2px] flex flex-wrap items-center gap-[6px]">
        <button
          type="button"
          onClick={() => actions.onPhotos(item)}
          className="rounded-full border border-[#EFF0F6] px-[10px] py-[2px] text-[11px] font-medium text-[#374151] hover:bg-[#F9FAFB] cursor-pointer"
        >
          Photos
        </button>
        {actions.canVerify &&
          VERDICTS.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={chosen === v.id}
              onClick={() => actions.onVerdict(item, v.id)}
              className={`rounded-full border px-[10px] py-[2px] text-[11px] font-medium cursor-pointer ${
                chosen === v.id ? `${v.active} font-semibold` : "border-[#EFF0F6] bg-white text-[#6B7280] hover:bg-[#F9FAFB]"
              }`}
            >
              {v.label}
            </button>
          ))}
        {!actions.canVerify && chosen && <span className="text-[11px] text-[#9CA3AF]">Confirmed: {chosen}</span>}
      </div>
    </article>
  );
}

/** One row for a run of repeats: the newest event, and on request the earlier ones it stands for. */
function EventFoldRow({ fold, now, actions }: { fold: EventFold<ApiShelfEvent>; now: Date; actions: RowActions }) {
  const [open, setOpen] = useState(false);
  const more = earlierText(fold.earlier.length);
  return (
    <div data-event-fold>
      <EventRow item={fold.head} now={now} actions={actions} />
      {more && (
        <button
          type="button"
          data-event-earlier
          aria-expanded={open}
          title="The same change of this product, earlier on"
          onClick={() => setOpen((o) => !o)}
          className="mb-[8px] rounded-full bg-[#F3F4F6] px-[10px] py-[2px] text-[11px] font-medium text-[#374151] hover:bg-[#E5E7EB] cursor-pointer"
        >
          {open ? "Hide earlier" : more}
        </button>
      )}
      {open && (
        <div className="mb-[8px] ml-[10px] divide-y divide-[#EFF0F6] border-l-2 border-[#EFF0F6] pl-[10px]">
          {fold.earlier.map((item) => (
            <EventRow key={`${item.store_id}|${item.event_key}`} item={item} now={now} actions={actions} />
          ))}
        </div>
      )}
    </div>
  );
}

interface PhotoSlotProps {
  title: string;
  url: string | null | undefined;
  /** The event's product in this photo. */
  boxes: Box[];
  /** The product's boxes in both photos: where the two photos zoom, so they show the same part of the shelf. */
  focus: Box[];
  onOpen: (url: string) => void;
}

function PhotoSlot({ title, url, boxes, focus, onOpen }: PhotoSlotProps) {
  // the frame's real size, learnt from the image: the zoom needs it
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const region = size && focus.length > 0 ? focusRegion(focus, size.w, size.h) : null;
  return (
    <figure className="flex flex-1 flex-col gap-[6px]">
      <figcaption className="text-[12px] font-semibold text-[#374151]">{title}</figcaption>
      {url ? (
        <button
          type="button"
          data-photo-open
          title="Open the whole photo large"
          onClick={() => onOpen(url)}
          className="cursor-zoom-in overflow-hidden rounded-[10px] border border-[#EFF0F6] hover:border-[#D1D5DB]"
        >
          {region && size ? (
            <svg
              data-photo-zoomed
              viewBox={`${region.x} ${region.y} ${region.w} ${region.h}`}
              preserveAspectRatio="xMidYMid meet"
              className="block w-full"
              role="img"
              aria-label={`${title}: the product's part of the shelf`}
            >
              <image href={url} x={0} y={0} width={size.w} height={size.h} />
              {boxes.map(([x, y, w, h], i) => (
                <rect
                  key={`${i}-${x}-${y}`}
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
              ))}
            </svg>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link, not a static asset
            <img
              src={url}
              alt={title}
              className="w-full object-contain"
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            />
          )}
        </button>
      ) : (
        <div className="flex aspect-video items-center justify-center rounded-[10px] border border-dashed border-[#E5E7EB] px-2 text-center text-[12px] text-[#9CA3AF]">
          {url === undefined ? "Loading..." : "Photo no longer kept"}
        </div>
      )}
      {url && focus.length > 0 && (
        <p data-photo-boxes className="text-[11.5px] leading-[1.4] text-[#6B7280]">
          {boxes.length === 0
            ? "None of this product in view"
            : `${boxes.length} ${boxes.length === 1 ? "box" : "boxes"} of this product`}
        </p>
      )}
    </figure>
  );
}

function PhotosDialog({ item, photos, onClose }: { item: ApiShelfEvent; photos: ApiEventPhotos | null | undefined; onClose: () => void }) {
  // photos === null: the links could not be loaded, shown as not kept
  const [large, setLarge] = useState<string | null>(null); // the photo opened large, over the dialog
  // Events written since boxes are kept: both photos zoom on the product's part of the shelf. Older ones show whole.
  const before = photos?.before_boxes ?? [];
  const after = photos?.after_boxes ?? [];
  const focus = [...before, ...after];
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (large) setLarge(null);
      else onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [large, onClose]);
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Event photos"
        className="w-full max-w-[720px] rounded-[18px] border border-[#EFF0F6] bg-white p-5 shadow-[0_12px_36px_rgba(0,0,0,0.16)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-[15px] font-semibold text-[#111827]">
            {eventLabel(item.type)} · {item.sku_name}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close photos"
            className="flex h-8 w-8 items-center justify-center rounded-full text-[#6B7280] hover:bg-[#F3F4F6] cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex flex-col gap-4 sm:flex-row">
          <PhotoSlot title="Before" url={photos === null ? null : photos?.before_url} boxes={before} focus={focus} onOpen={setLarge} />
          <PhotoSlot title="At the event" url={photos === null ? null : photos?.after_url} boxes={after} focus={focus} onOpen={setLarge} />
        </div>
      </div>
      {large && (
        <div
          data-photo-large
          role="dialog"
          aria-modal="true"
          aria-label="Photo"
          className="fixed inset-0 z-[70] flex cursor-zoom-out items-center justify-center bg-black/85 p-4"
          onClick={(e) => {
            e.stopPropagation();
            setLarge(null);
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link, not a static asset */}
          <img src={large} alt="" className="max-h-full max-w-full object-contain" />
        </div>
      )}
    </div>
  );
}

/** Shelf events of the Dashboard filters, newest first: out of stock, low stock, depleted, restocked. */
export function RecentActivitiesCard({ load, reloadKey, blockedText, accuracyLine, accuracyByType, canVerify, loadPhotos, saveVerdict, onFirstPage }: RecentActivitiesCardProps) {
  const [kind, setKind] = useState<ActivityKind>("all");
  const [items, setItems] = useState<ApiShelfEvent[] | null>(null);
  const [allOpen, setAllOpen] = useState(false);
  const [all, setAll] = useState<ApiShelfEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, ShelfVerdict>>({});
  const [photoOf, setPhotoOf] = useState<ApiShelfEvent | null>(null);
  const [photos, setPhotos] = useState<ApiEventPhotos | null | undefined>(undefined);
  const wantedPhotos = useRef<string | null>(null); // the event whose photos were asked for last
  const now = new Date();
  const idOf = (item: ApiShelfEvent) => `${item.store_id}|${item.event_key}`;

  const actions: RowActions = {
    canVerify: canVerify && !!saveVerdict,
    verdictOf: (item) => chosen[idOf(item)] ?? item.verdict,
    onVerdict: (item, verdict) => {
      if (!saveVerdict) return;
      const before = chosen[idOf(item)];
      setChosen((prev) => ({ ...prev, [idOf(item)]: verdict }));
      saveVerdict(item.store_id, item.event_key, verdict).catch(() =>
        setChosen((prev) => {
          const next = { ...prev };
          if (before) next[idOf(item)] = before;
          else delete next[idOf(item)];
          return next;
        })
      );
    },
    onPhotos: (item) => {
      const id = idOf(item);
      wantedPhotos.current = id;
      setPhotoOf(item);
      setPhotos(undefined);
      if (!loadPhotos) return setPhotos(null);
      // an answer for an event that is no longer the open one is dropped
      const settle = (value: ApiEventPhotos | null) => {
        if (wantedPhotos.current === id) setPhotos(value);
      };
      loadPhotos(item.store_id, item.event_key).then(settle, () => settle(null));
    },
  };

  useEffect(() => {
    if (!load) return;
    let cancelled = false;
    load(kind)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        if (kind === "all") onFirstPage?.(res.items, res.next_cursor !== null);
      })
      .catch(() => {
        if (!cancelled) setItems(null);
      });
    return () => {
      cancelled = true;
    };
  }, [load, kind, reloadKey, onFirstPage]);

  const loadMore = async (from?: string) => {
    if (!load) return;
    const res = await load(kind, from);
    setAll((prev) => (from ? [...prev, ...res.items] : res.items));
    setCursor(res.next_cursor);
  };

  const empty = blockedText ?? (kind === "all" ? "No shelf activity in this period." : "No matching shelf activity in this period.");

  return (
    <div id="recent-shelf-activities" className="flex h-[440px] scroll-mt-4 flex-col overflow-hidden rounded-[18px] border border-[#EFF0F6] bg-white">
      <div className="shrink-0 border-b border-[#EFF0F6] px-[20px] pt-[14px] pb-[12px]">
        <h2 className="text-[18px] font-semibold leading-[1.3] text-[#111827]">Recent Shelf Activities</h2>
        <p className="mt-[2px] text-[11.5px] leading-[1.4] text-[#9CA3AF]">
          Changes on the shelf that held for two checks in a row (10 minutes), opening hours only.
        </p>
        {accuracyLine && (
          <p data-alert-accuracy className="mt-[4px] text-[12px] font-medium leading-[1.4] text-[#374151]">
            {accuracyLine}
          </p>
        )}
        {accuracyByType && (
          <p data-alert-accuracy-by-type className="text-[11.5px] leading-[1.4] text-[#6B7280]">
            {accuracyByType}
          </p>
        )}
        <div className="mt-[8px] flex flex-wrap items-center gap-[8px]">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              aria-pressed={kind === opt.id}
              onClick={() => setKind(opt.id)}
              className={`rounded-full px-[10px] py-[4px] text-[12px] leading-tight transition-colors cursor-pointer ${
                kind === opt.id
                  ? "bg-[#F3F4F6] font-semibold text-[#111827]"
                  : "border border-[#EFF0F6] bg-white font-medium text-[#6B7280] hover:bg-[#F9FAFB]"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div data-shelf-events className="flex-1 overflow-y-auto px-[20px] py-[6px]">
        {!items || items.length === 0 ? (
          <div className="flex h-full items-center justify-center px-4 text-center text-[13px] text-[#9CA3AF]">
            {items === null && !blockedText ? "Shelf activity appears once your account is approved." : empty}
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F6]">
            {foldEvents(items).map((fold) => (
              <EventFoldRow key={idOf(fold.head)} fold={fold} now={now} actions={actions} />
            ))}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-[#EFF0F6] px-[20px] py-[12px]">
        <button
          type="button"
          disabled={!load}
          onClick={() => {
            setAllOpen(true);
            void loadMore();
          }}
          className="text-[13px] font-medium text-[#6B7280] hover:text-[#111827] transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
        >
          View all activity
        </button>
      </div>

      {allOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-[1px]"
          onClick={() => setAllOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="all-activity-title"
            className="flex max-h-[80vh] w-full max-w-[640px] flex-col overflow-hidden rounded-[18px] border border-[#EFF0F6] bg-white shadow-[0_12px_36px_rgba(0,0,0,0.16)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#EFF0F6] px-5 py-4">
              <div>
                <h3 id="all-activity-title" className="text-[16px] font-semibold text-[#111827]">
                  All shelf activity
                </h3>
                <p className="text-[12px] text-[#6B7280]">
                  {all.length} {all.length === 1 ? "event" : "events"} shown, newest first
                </p>
              </div>
              <button
                type="button"
                onClick={() => setAllOpen(false)}
                aria-label="Close all shelf activity"
                className="flex h-8 w-8 items-center justify-center rounded-full text-[#6B7280] hover:bg-[#F3F4F6] hover:text-[#111827] cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 divide-y divide-[#EFF0F6] overflow-y-auto px-5 py-2">
              {all.length === 0 ? (
                <p className="py-6 text-center text-[13px] text-[#6B7280]">{empty}</p>
              ) : (
                foldEvents(all).map((fold) => <EventFoldRow key={idOf(fold.head)} fold={fold} now={now} actions={actions} />)
              )}
            </div>
            {cursor && (
              <div className="flex justify-center border-t border-[#EFF0F6] px-5 py-3">
                <button
                  type="button"
                  onClick={() => void loadMore(cursor)}
                  className="rounded-[8px] bg-[#F3F4F6] px-4 py-1.5 text-[13px] font-medium text-[#111827] hover:bg-[#E5E7EB] cursor-pointer"
                >
                  Load more
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      {photoOf && <PhotosDialog item={photoOf} photos={photos} onClose={() => {
        wantedPhotos.current = null;
        setPhotoOf(null);
      }} />}
    </div>
  );
}
