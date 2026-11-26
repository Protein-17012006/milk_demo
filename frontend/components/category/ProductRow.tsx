"use client";

import React, { useState } from "react";
import Image from "next/image";
import type { CategoryColumns, SkuProduct } from "@/lib/products-ui";
import { BADGE_COLORS, badgeLabel, badgePillText, reliabilityText } from "@/lib/reliability-ui";
import { shownConfidence } from "@/lib/products-ui";

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.7) return "#1A932E";
  if (confidence >= 0.5) return "#FFCC00";
  return "#FF8D28";
}

interface ProductRowProps {
  item: SkuProduct;
  /** A variant shown under its product-line group row: the product cell is indented. */
  nested?: boolean;
  /** Which of the optional columns this account sees (lib/products-ui categoryColumns). */
  columns: CategoryColumns;
  onOpenDetails(): void;
}

/** One SKU of the Category table (one row of the Datagent CV Output view). */
export function ProductRow({ item, nested = false, columns, onOpenDetails }: ProductRowProps) {
  const barWidthPct = Math.min(100, Math.max(12, Math.round(item.confidence * 100)));
  const barColor = getConfidenceColor(item.confidence);
  const confidence = shownConfidence(item.onShelfStock, item.confidence);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const reliability = item.reliability;

  return (
    <div
      data-sku-row
      data-sku-id={item.id}
      className={`rounded-[10px] border border-[#EFF0F6] px-[16px] py-[12px] transition-colors hover:border-[#D1D5DB] ${
        nested ? "bg-[#FCFCFD]" : "bg-white"
      }`}
    >
      <div className="flex min-h-[48px] items-center">
        {/* Product Thumbnail + Name */}
        <div
          className={`flex flex-[2.4] min-w-[240px] items-center gap-[12px] pr-[12px] ${
            nested ? "pl-[28px]" : ""
          }`}
        >
          <div className="relative h-[44px] w-[44px] shrink-0 overflow-hidden rounded-[10px] border border-black/15 bg-white shadow-[-2px_3px_4px_rgba(0,0,0,0.16)]">
            <Image
              src={item.thumbnail}
              alt={item.name}
              width={44}
              height={44}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="flex min-w-0 flex-col items-start gap-[4px]">
            <button
              type="button"
              onClick={onOpenDetails}
              className="line-clamp-2 text-left text-[13px] font-semibold leading-[18px] text-[#111827] hover:text-[#EE730A] transition-colors cursor-pointer"
            >
              {item.name}
            </button>
            {reliability && (
              <button
                type="button"
                data-reliability={reliability.badge}
                aria-expanded={detailsOpen}
                aria-label={`Reliability of ${item.name}: ${badgeLabel(reliability.badge)}`}
                title={reliabilityText(reliability)}
                onClick={() => setDetailsOpen((open) => !open)}
                className={`whitespace-nowrap rounded-full px-[8px] py-[1px] text-[10.5px] font-semibold leading-tight cursor-pointer ${BADGE_COLORS[reliability.badge]}`}
              >
                {badgePillText(reliability.badge)}
              </button>
            )}
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex w-[126px] shrink-0 flex-wrap items-center gap-[4px] pr-[12px]">
          {item.categories.map((tag) => (
            <span
              key={tag}
              className="rounded-[6px] bg-[#F3F4F6] px-[8px] py-[3px] text-[11px] font-medium leading-tight text-[#374151]"
            >
              {tag}
            </span>
          ))}
          {item.hasMoreCategories && (
            <span className="rounded-[6px] bg-[#F3F4F6] px-[6px] py-[3px] text-[11px] font-medium leading-tight text-[#374151]">
              ...
            </span>
          )}
        </div>

        {/* Pack */}
        <div className="flex w-[82px] shrink-0 flex-col gap-[2px] pr-[12px]">
          <span className="text-[13px] font-medium leading-tight text-[#111827]">
            {item.packType}
          </span>
          <span className="text-[12px] font-normal leading-tight text-[#6B7280]">
            {item.packSize}
          </span>
        </div>

        {/* SKU Code + Barcode (the team) */}
        {columns.skuCode && (
          <div data-col="sku-code" className="flex w-[152px] shrink-0 flex-col gap-[2px] pr-[12px]">
            <span className="text-[12px] font-medium leading-tight text-[#111827]">
              {item.skuCode}
            </span>
            <span className="text-[11px] font-normal leading-tight text-[#9CA3AF]">
              {item.barcode}
            </span>
          </div>
        )}

        {/* On-Shelf Stock */}
        <div className="flex w-[140px] shrink-0 items-baseline gap-[4px] pr-[12px]">
          <span className="text-[15px] font-semibold text-[#111827]">
            {item.onShelfStock}
          </span>
          <span className="text-[12px] font-normal text-[#6B7280]">units</span>
        </div>

        {/* Confidence + Progress Bar (the team) */}
        {columns.confidence && (
          <div
            data-col="confidence"
            className="flex w-[140px] shrink-0 flex-col gap-[6px] pr-[12px]"
            title={
              confidence === null
                ? "No units at the last check, so there is no reading to score"
                : `Confidence ${confidence.toFixed(2)}${item.cvOutput.is_flagged ? ", flagged for review" : ""}`
            }
          >
            <div className="flex items-center gap-[6px]">
              <span className="text-[13px] font-semibold leading-none text-[#111827]">
                {confidence === null ? "—" : `${Math.round(confidence * 100)}%`}
              </span>
              {item.cvOutput.is_flagged && (
                <span className="rounded bg-[#FFF7ED] px-1.5 py-[1px] text-[10px] font-semibold text-[#C2560A]">
                  Flagged
                </span>
              )}
            </div>
            {confidence !== null && (
              <div className="h-[4px] w-[72px] overflow-hidden rounded-[2px] bg-[#EEF0F3]">
                <div
                  className="h-full rounded-[2px]"
                  style={{ width: `${barWidthPct}%`, backgroundColor: barColor }}
                />
              </div>
            )}
          </div>
        )}

        {/* Avail In Stores (more than one store) */}
        {columns.stores && (
          <div data-col="stores" className="flex w-[128px] shrink-0 items-baseline gap-[1px] pr-[12px]">
            <span className="text-[18px] font-semibold leading-none text-[#111827]">
              {item.storesAvailable}
            </span>
            <span className="text-[12px] font-normal leading-none text-[#6B7280]">
              /{item.storesTotal} stores
            </span>
          </div>
        )}

        {/* Actions */}
        <div className="flex w-[64px] shrink-0 items-center justify-end">
          <button
            type="button"
            onClick={onOpenDetails}
            className="flex h-[28px] items-center rounded-[6px] border border-[#E5E7EB] bg-white px-[12px] text-[12px] font-medium text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
          >
            View
          </button>
        </div>
      </div>
      {reliability && detailsOpen && (
        <p data-reliability-details className="mt-[8px] pl-[56px] text-[12px] leading-[16px] text-[#6B7280]">
          {reliabilityText(reliability)}
        </p>
      )}
    </div>
  );
}
