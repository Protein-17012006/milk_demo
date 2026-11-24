"use client";

import React, { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ApiShelfEvent, ApiShelfEventsResponse, ShelfEventType } from "@/lib/api";
import { eventLabel, eventText, oosDurationText, timeAgo } from "@/lib/shelf-ui";

export type ActivityKind = "all" | "alerts" | "restocked";

interface RecentActivitiesCardProps {
  /** Loads one page of events for the Dashboard filters; null while signed out. */
  load: ((kind: ActivityKind, cursor?: string) => Promise<ApiShelfEventsResponse>) | null;
  /** Changes whenever the Dashboard filters change, so the card loads again. */
  reloadKey: string;
  /** Shown instead of an empty list when the shelf numbers are blocked (for example, no opening hours). */
  blockedText: string | null;
}

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

function EventRow({ item, now }: { item: ApiShelfEvent; now: Date }) {
  return (
    <article data-shelf-event={item.type} className="flex flex-col gap-[4px] py-[9px]">
      <div className="flex items-center gap-[8px]">
        <span className={`shrink-0 rounded-full px-[10px] py-[2px] text-[11px] font-semibold leading-tight ${BADGE_STYLES[item.type]}`}>
          {eventLabel(item.type)}
        </span>
        <h3 className="truncate text-[13px] font-semibold leading-[18px] text-[#111827]">{item.sku_name}</h3>
      </div>
      <span className="text-[12px] leading-[16px] text-[#9CA3AF]">{timeAgo(item.at, now)}</span>
      <span className="text-[12px] leading-[16px] text-[#6B7280]">{item.store_name}</span>
      <span className="text-[12px] font-medium leading-[16px] text-[#374151]">
        {eventText(item)}
        {oosDurationText(item)}
      </span>
    </article>
  );
}

/** Shelf events of the Dashboard filters, newest first: out of stock, low stock, depleted, restocked. */
export function RecentActivitiesCard({ load, reloadKey, blockedText }: RecentActivitiesCardProps) {
  const [kind, setKind] = useState<ActivityKind>("all");
  const [items, setItems] = useState<ApiShelfEvent[] | null>(null);
  const [allOpen, setAllOpen] = useState(false);
  const [all, setAll] = useState<ApiShelfEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const now = new Date();

  useEffect(() => {
    if (!load) return;
    let cancelled = false;
    load(kind)
      .then((res) => {
        if (!cancelled) setItems(res.items);
      })
      .catch(() => {
        if (!cancelled) setItems(null);
      });
    return () => {
      cancelled = true;
    };
  }, [load, kind, reloadKey]);

  const loadMore = async (from?: string) => {
    if (!load) return;
    const res = await load(kind, from);
    setAll((prev) => (from ? [...prev, ...res.items] : res.items));
    setCursor(res.next_cursor);
  };

  const empty = blockedText ?? (kind === "all" ? "No shelf activity in this period." : "No matching shelf activity in this period.");

  return (
    <div className="flex h-[440px] flex-col overflow-hidden rounded-[18px] border border-[#EFF0F6] bg-white">
      <div className="shrink-0 border-b border-[#EFF0F6] px-[20px] pt-[14px] pb-[12px]">
        <h2 className="text-[18px] font-semibold leading-[1.3] text-[#111827]">Recent Shelf Activities</h2>
        <p className="mt-[2px] text-[11.5px] leading-[1.4] text-[#9CA3AF]">
          Changes on the shelf that held for two checks in a row (10 minutes), opening hours only.
        </p>
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
            {items === null && !blockedText ? "Sign in with an approved account to see shelf activity." : empty}
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F6]">
            {items.map((item) => (
              <EventRow key={`${item.store_id}|${item.event_key}`} item={item} now={now} />
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
                all.map((item) => <EventRow key={`${item.store_id}|${item.event_key}`} item={item} now={now} />)
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
    </div>
  );
}
