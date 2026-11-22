"use client";

import React from "react";
import Image from "next/image";
import { Check, ChevronRight, Minus } from "lucide-react";
import type { ProductGroup } from "@/lib/product-groups";
import { getConfidenceColor } from "./ProductRow";

interface ProductGroupRowProps {
  group: ProductGroup;
  expanded: boolean;
  selection: "all" | "some" | "none";
  onToggleExpand(): void;
  onToggleSelect(): void;
}

/** Summary row of one product line (brand · subcategory); its SKUs render under it when expanded. */
export function ProductGroupRow({
  group,
  expanded,
  selection,
  onToggleExpand,
  onToggleSelect,
}: ProductGroupRowProps) {
  const n = group.variants.length;
  const conf = group.confidence;
  const barWidthPct = conf === null ? 0 : Math.min(100, Math.max(12, Math.round(conf * 100)));

  return (
    <div
      data-group-row
      data-group-key={group.key}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
      aria-label={`${group.label}: ${expanded ? "hide" : "show"} ${n} variants`}
      onClick={onToggleExpand}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggleExpand();
        }
      }}
      className={`flex min-h-[64px] items-center rounded-[10px] border bg-white px-[16px] py-[10px] transition-colors cursor-pointer ${
        selection === "all" ? "border-[#969696]" : "border-[#E5E7EB] hover:border-[#D1D5DB]"
      }`}
    >
      {/* Tri-state checkbox: selects every visible variant of the group */}
      <div className="w-[32px] shrink-0 flex items-center">
        <button
          type="button"
          role="checkbox"
          aria-checked={selection === "all" ? true : selection === "some" ? "mixed" : false}
          aria-label={`Select ${group.label}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect();
          }}
          className={`flex h-[16px] w-[16px] items-center justify-center rounded-[4px] transition-colors cursor-pointer ${
            selection === "none"
              ? "border-[1.5px] border-[#D1D5DB] bg-white hover:border-[#9CA3AF]"
              : "bg-[#515151] text-white"
          }`}
        >
          {selection === "all" && <Check className="h-[11px] w-[11px]" strokeWidth={3} />}
          {selection === "some" && <Minus className="h-[11px] w-[11px]" strokeWidth={3} />}
        </button>
      </div>

      {/* Product line */}
      <div className="flex flex-[2.4] min-w-[240px] items-center gap-[10px] pr-[12px]">
        <ChevronRight
          className={`h-[16px] w-[16px] shrink-0 text-[#6B7280] transition-transform ${
            expanded ? "rotate-90" : ""
          }`}
          strokeWidth={2}
        />
        <div className="relative h-[40px] w-[40px] shrink-0 overflow-hidden rounded-[10px] border border-black/15 bg-white">
          <Image
            src={group.thumbnail}
            alt=""
            width={40}
            height={40}
            className="h-full w-full object-cover"
          />
        </div>
        <div className="min-w-0">
          <p className="line-clamp-2 text-[13.5px] font-semibold leading-[18px] text-[#111827]">
            {group.label}
          </p>
          <p className="text-[12px] leading-[16px] text-[#6B7280]">
            {n} {n === 1 ? "variant" : "variants"} · {group.variantsOnShelf} on shelf
          </p>
        </div>
      </div>

      {/* Category */}
      <div className="flex w-[126px] shrink-0 items-center pr-[12px]">
        <span className="rounded-[6px] bg-[#F3F4F6] px-[8px] py-[3px] text-[11px] font-medium leading-tight text-[#374151]">
          {group.primaryCategory}
        </span>
      </div>

      {/* Pack */}
      <div className="w-[82px] shrink-0 pr-[12px] text-[12.5px] font-medium leading-tight text-[#111827]">
        {group.packLabel}
      </div>

      {/* SKU count */}
      <div className="w-[152px] shrink-0 pr-[12px] text-[12px] font-medium text-[#6B7280]">
        {n} {n === 1 ? "SKU" : "SKUs"}
      </div>

      {/* Total on-shelf stock */}
      <div className="flex w-[140px] shrink-0 items-baseline gap-[4px] pr-[12px]">
        <span className="text-[15px] font-semibold text-[#111827]">{group.totalUnits}</span>
        <span className="text-[12px] font-normal text-[#6B7280]">units</span>
      </div>

      {/* Unit-weighted confidence */}
      <div
        className="flex w-[140px] shrink-0 flex-col gap-[6px] pr-[12px]"
        title="Average confidence weighted by units, over the variants on the shelf"
      >
        <div className="flex items-center gap-[6px]">
          <span className="text-[13px] font-semibold leading-none text-[#111827]">
            {conf === null ? "—" : `${Math.round(conf * 100)}%`}
          </span>
          {group.flaggedCount > 0 && (
            <span className="rounded bg-[#FFF7ED] px-1.5 py-[1px] text-[10px] font-semibold text-[#C2560A]">
              {group.flaggedCount} flagged
            </span>
          )}
        </div>
        {conf !== null && (
          <div className="h-[4px] w-[72px] overflow-hidden rounded-[2px] bg-[#EEF0F3]">
            <div
              className="h-full rounded-[2px]"
              style={{ width: `${barWidthPct}%`, backgroundColor: getConfidenceColor(conf) }}
            />
          </div>
        )}
      </div>

      {/* Stores */}
      <div className="flex w-[128px] shrink-0 items-baseline gap-[1px] pr-[12px]">
        <span className="text-[18px] font-semibold leading-none text-[#111827]">
          {group.storesAvailable}
        </span>
        <span className="text-[12px] font-normal leading-none text-[#6B7280]">
          /{group.storesTotal} stores
        </span>
      </div>

      {/* No actions: View belongs to each SKU */}
      <div className="w-[90px] shrink-0" />
    </div>
  );
}
