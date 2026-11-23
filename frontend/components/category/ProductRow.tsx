"use client";

import React from "react";
import Image from "next/image";
import { Check, MoreHorizontal } from "lucide-react";
import type { SkuProduct } from "@/lib/products-ui";

export function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.7) return "#1A932E";
  if (confidence >= 0.5) return "#FFCC00";
  return "#FF8D28";
}

interface ProductRowProps {
  item: SkuProduct;
  selected: boolean;
  /** A variant shown under its product-line group row: the product cell is indented. */
  nested?: boolean;
  menuOpen: boolean;
  menuRef: React.RefObject<HTMLDivElement | null>;
  onToggleSelect(): void;
  onOpenDetails(): void;
  onToggleMenu(): void;
  onCopyCode(): void;
  onExportRow(): void;
}

/** One SKU of the Products table (one row of the Datagent CV Output view). */
export function ProductRow({
  item,
  selected,
  nested = false,
  menuOpen,
  menuRef,
  onToggleSelect,
  onOpenDetails,
  onToggleMenu,
  onCopyCode,
  onExportRow,
}: ProductRowProps) {
  const barWidthPct = Math.min(100, Math.max(12, Math.round(item.confidence * 100)));
  const barColor = getConfidenceColor(item.confidence);

  return (
    <div
      data-sku-row
      data-sku-id={item.id}
      className={`flex min-h-[72px] items-center rounded-[10px] px-[16px] py-[12px] transition-colors ${
        nested ? "bg-[#FCFCFD]" : "bg-white"
      } ${
        selected
          ? "border border-[#969696]"
          : "border border-[#EFF0F6] hover:border-[#D1D5DB]"
      }`}
    >
      {/* Checkbox */}
      <div className="w-[32px] shrink-0 flex items-center">
        <button
          type="button"
          role="checkbox"
          aria-checked={selected}
          aria-label={`Select ${item.name}`}
          onClick={onToggleSelect}
          className={`flex h-[16px] w-[16px] items-center justify-center rounded-[4px] transition-colors cursor-pointer ${
            selected
              ? "bg-[#515151] text-white"
              : "border-[1.5px] border-[#D1D5DB] bg-white hover:border-[#9CA3AF]"
          }`}
        >
          {selected && <Check className="h-[11px] w-[11px]" strokeWidth={3} />}
        </button>
      </div>

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
        <button
          type="button"
          onClick={onOpenDetails}
          className="line-clamp-2 text-left text-[13px] font-semibold leading-[18px] text-[#111827] hover:text-[#EE730A] transition-colors cursor-pointer"
        >
          {item.name}
        </button>
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

      {/* SKU Code + Barcode */}
      <div className="flex w-[152px] shrink-0 flex-col gap-[2px] pr-[12px]">
        <span className="text-[12px] font-medium leading-tight text-[#111827]">
          {item.skuCode}
        </span>
        <span className="text-[11px] font-normal leading-tight text-[#9CA3AF]">
          {item.barcode}
        </span>
      </div>

      {/* On-Shelf Stock */}
      <div className="flex w-[140px] shrink-0 items-baseline gap-[4px] pr-[12px]">
        <span className="text-[15px] font-semibold text-[#111827]">
          {item.onShelfStock}
        </span>
        <span className="text-[12px] font-normal text-[#6B7280]">units</span>
      </div>

      {/* Confidence + Progress Bar */}
      <div
        className="flex w-[140px] shrink-0 flex-col gap-[6px] pr-[12px]"
        title={`confidence_score: ${item.confidence.toFixed(2)} · is_flagged: ${item.cvOutput.is_flagged ? "TRUE" : "FALSE"}`}
      >
        <div className="flex items-center gap-[6px]">
          <span className="text-[13px] font-semibold leading-none text-[#111827]">
            {Math.round(item.confidence * 100)}%
          </span>
          {item.cvOutput.is_flagged && (
            <span className="rounded bg-[#FFF7ED] px-1.5 py-[1px] text-[10px] font-semibold text-[#C2560A]">
              Flagged
            </span>
          )}
        </div>
        <div className="h-[4px] w-[72px] overflow-hidden rounded-[2px] bg-[#EEF0F3]">
          <div
            className="h-full rounded-[2px]"
            style={{ width: `${barWidthPct}%`, backgroundColor: barColor }}
          />
        </div>
      </div>

      {/* Avail In Stores */}
      <div className="flex w-[128px] shrink-0 items-baseline gap-[1px] pr-[12px]">
        <span className="text-[18px] font-semibold leading-none text-[#111827]">
          {item.storesAvailable}
        </span>
        <span className="text-[12px] font-normal leading-none text-[#6B7280]">
          /{item.storesTotal} stores
        </span>
      </div>

      {/* Actions */}
      <div className="relative flex w-[90px] shrink-0 items-center justify-end gap-[6px]">
        <button
          type="button"
          onClick={onOpenDetails}
          className="flex h-[28px] items-center rounded-[6px] border border-[#E5E7EB] bg-white px-[12px] text-[12px] font-medium text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
        >
          View
        </button>
        <button
          type="button"
          onClick={onToggleMenu}
          aria-label={`More actions for ${item.name}`}
          className="flex h-[28px] w-[28px] items-center justify-center rounded-[6px] border border-[#E5E7EB] bg-white text-[#111827] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors cursor-pointer"
        >
          <MoreHorizontal className="h-[15px] w-[15px]" />
        </button>

        {menuOpen && (
          <div
            ref={menuRef}
            className="absolute right-0 top-[34px] z-20 w-[160px] rounded-[10px] border border-[#E5E7EB] bg-white p-1 shadow-[0_8px_22px_rgba(0,0,0,0.08)]"
          >
            <button
              type="button"
              onClick={() => {
                onToggleMenu();
                onOpenDetails();
              }}
              className="flex w-full rounded-[7px] px-2.5 py-1.5 text-left text-[12px] text-[#111827] hover:bg-[#F7F8FA] cursor-pointer"
            >
              View Validation Details
            </button>
            <button
              type="button"
              onClick={() => {
                onToggleMenu();
                onCopyCode();
              }}
              className="flex w-full rounded-[7px] px-2.5 py-1.5 text-left text-[12px] text-[#111827] hover:bg-[#F7F8FA] cursor-pointer"
            >
              Copy SKU Code
            </button>
            <button
              type="button"
              onClick={() => {
                onToggleMenu();
                onExportRow();
              }}
              className="flex w-full rounded-[7px] px-2.5 py-1.5 text-left text-[12px] text-[#111827] hover:bg-[#F7F8FA] cursor-pointer"
            >
              Export Row CSV
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
