"use client";

import React from "react";
import Image from "next/image";
import { Camera, Loader2 } from "lucide-react";
import { productThumbnail } from "@/lib/product-thumbnail";
import { BADGE_COLORS, badgePillText } from "@/lib/reliability-ui";
import { notInViewText, stockStatusLabel, type ShelfNowRow, type StockStatus } from "@/lib/shelf-now";

interface ShelfNowTableProps {
  /** The plan's products at the latest reading; null until the product list has come back. */
  rows: ShelfNowRow[] | null;
  /** The product list could not be read. */
  failed: boolean;
  /** Said in place of the rows when the account cannot read them yet (it waits for approval). */
  notice?: string | null;
  /** Opens the latest shelf photo; left out while there is no product list to take it from. */
  onOpenPhoto?: () => void;
  /** Why the photo cannot be opened (no frame was stored, or it did not load); null when it can. */
  photoReason?: string | null;
  /** The photo link is being renewed. */
  photoBusy?: boolean;
}

const STATUS_COLORS: Record<StockStatus, string> = {
  OOS: "bg-[#FEE2E2] text-[#DC2626]",
  LOW: "bg-[#FEF3C7] text-[#B45309]",
  IN_STOCK: "bg-[#E8F5E9] text-[#2E7D32]",
  NOT_IN_VIEW: "bg-[#F3F4F6] text-[#6B7280]",
};

/** What is on the shelf now, product by product: the first thing a viewer opens the Dashboard for. */
export function ShelfNowTable({ rows, failed, notice = null, onOpenPhoto, photoReason = null, photoBusy = false }: ShelfNowTableProps) {
  const message =
    notice ??
    (failed
      ? "The product list could not be loaded."
      : rows === null
        ? "Loading…"
        : rows.length === 0
          ? "No shelf plan yet. An administrator sets it in Settings."
          : null);

  return (
    <div data-shelf-now className="flex h-full flex-col rounded-[18px] border border-[#EFF0F6] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-[#EFF0F6] px-[20px] pt-[16px] pb-[12px]">
        <div className="min-w-0">
          <h2 className="text-[18px] font-semibold leading-[1.3] text-[#111827]">On the shelf now</h2>
          <p className="mt-[2px] text-[11.5px] leading-[1.4] text-[#9CA3AF]">
            Each product on the shelf plan, at the latest reading.
          </p>
        </div>
        {onOpenPhoto && (
          <div className="flex flex-col items-end gap-[3px]">
            <button
              type="button"
              data-shelf-photo
              disabled={Boolean(photoReason) || photoBusy}
              title={photoReason ?? "The frame these numbers were read from, with each product's boxes"}
              onClick={onOpenPhoto}
              className="inline-flex h-[32px] items-center gap-[6px] whitespace-nowrap rounded-[8px] border border-[#E5E7EB] bg-white px-[12px] text-[12.5px] font-medium text-[#111827] transition-colors hover:bg-[#F9FAFB] disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
            >
              {photoBusy ? <Loader2 className="h-[14px] w-[14px] animate-spin" /> : <Camera className="h-[14px] w-[14px]" strokeWidth={1.9} />}
              <span>Shelf photo</span>
            </button>
            {photoReason && (
              <span data-shelf-photo-reason className="max-w-[220px] text-right text-[11px] leading-[1.35] text-[#6B7280]">
                {photoReason}
              </span>
            )}
          </div>
        )}
      </div>

      {message ? (
        <p data-shelf-now-message className="px-[20px] py-[28px] text-center text-[13px] text-[#6B7280]">
          {message}
        </p>
      ) : (
        <ul className="max-h-[430px] divide-y divide-[#EFF0F6] overflow-y-auto px-[20px]">
          {(rows ?? []).map((row) => (
            <li
              key={row.skuId}
              data-shelf-now-row
              data-status={row.status}
              // On a phone the name keeps the whole first line and the count sits under it: a name cut to
              // "Slide Chees…" could be any of four products.
              className="flex flex-wrap items-center gap-x-[12px] gap-y-[6px] py-[10px]"
            >
              <div className="h-[36px] w-[36px] shrink-0 overflow-hidden rounded-[8px] border border-black/15 bg-white">
                <Image
                  src={productThumbnail(row.imageUrl)}
                  alt=""
                  width={36}
                  height={36}
                  className="h-full w-full object-cover"
                />
              </div>
              <div className="min-w-0 flex-1 basis-[calc(100%-48px)] sm:basis-0">
                <p className="line-clamp-2 text-[13px] font-semibold leading-[17px] text-[#111827]">{row.name}</p>
                {row.notInView && (
                  <p data-not-in-view className="mt-[2px] text-[11.5px] leading-[1.35] text-[#6B7280]">
                    {notInViewText(row.notInView, new Date())}
                  </p>
                )}
                {row.badge && (
                  <span
                    data-reliability={row.badge}
                    title="How far this product's count can be trusted, from the frames the team checked in the last 14 days"
                    className={`mt-[3px] inline-block whitespace-nowrap rounded-full px-[8px] py-[1px] text-[10.5px] font-semibold leading-tight ${BADGE_COLORS[row.badge]}`}
                  >
                    {badgePillText(row.badge)}
                  </span>
                )}
              </div>
              <div className="ml-[48px] flex shrink-0 items-center gap-[12px] sm:ml-0">
                <p className="whitespace-nowrap text-right">
                  <span data-units={row.units} className="text-[17px] font-bold leading-none text-[#111827]">
                    {row.status === "NOT_IN_VIEW" ? "–" : row.units}
                  </span>
                  {row.status !== "NOT_IN_VIEW" && (
                    <>
                      {" "}
                      <span className="text-[12px] text-[#6B7280]">{row.units === 1 ? "unit" : "units"}</span>
                    </>
                  )}
                </p>
                <span
                  className={`w-[92px] shrink-0 rounded-full px-[10px] py-[3px] text-center text-[11.5px] font-semibold leading-tight ${STATUS_COLORS[row.status]}`}
                >
                  {stockStatusLabel(row.status)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
