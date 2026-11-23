"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import {
  ALL_STORES_LABEL,
  TIMEFRAME_OPTIONS,
  CATEGORY_OPTIONS,
  type TimeframeOption,
  type CategoryOption,
} from "@/lib/reports-ui";

interface FilterBarProps {
  timeframe: TimeframeOption;
  store: string;
  category: CategoryOption;
  storeOptions?: string[];
  onTimeframeChange: (value: TimeframeOption) => void;
  onStoreChange: (value: string) => void;
  onCategoryChange: (value: CategoryOption) => void;
}

interface FilterDropdownProps<T extends string> {
  label: string;
  value: T;
  options: T[];
  onChange: (value: T) => void;
}

function FilterDropdown<T extends string>({
  label,
  value,
  options,
  onChange,
}: FilterDropdownProps<T>) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleOutsideClick);
    }
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className="flex h-[45px] w-full items-center justify-between rounded-[18px] border border-[#EFF0F6] bg-white px-[18px] text-[14.5px] font-medium tracking-[-0.018em] transition-colors hover:border-[#D9DCE8] cursor-pointer"
      >
        <span className="truncate">
          <span className="text-black/70">{label}: </span>
          <span className="text-black">{value}</span>
        </span>
        {/* Small solid downward triangle matching Figma Icon / Arrow Full Down */}
        <svg
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          aria-hidden="true"
          className={`ml-2 shrink-0 text-black transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
        >
          <path d="M5 6L0.669873 0.75L9.33013 0.75L5 6Z" fill="currentColor" />
        </svg>
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-[51px] z-30 rounded-[14px] border border-[#EFF0F6] bg-white p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.08)]"
        >
          {options.map((opt) => {
            const selected = opt === value;
            return (
              <li key={opt}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    onChange(opt);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-[10px] px-3 py-2 text-left text-[13.5px] transition-colors cursor-pointer ${
                    selected
                      ? "bg-[#FFF5EC] font-medium text-[#EE730A]"
                      : "text-black/80 hover:bg-[#F7F7F7]"
                  }`}
                >
                  <span>{opt}</span>
                  {selected && <Check className="h-3.5 w-3.5 shrink-0" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function FilterBar({
  timeframe,
  store,
  category,
  storeOptions,
  onTimeframeChange,
  onStoreChange,
  onCategoryChange,
}: FilterBarProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <FilterDropdown
        label="Timeframe"
        value={timeframe}
        options={TIMEFRAME_OPTIONS}
        onChange={onTimeframeChange}
      />
      <FilterDropdown
        label="Store"
        value={store}
        options={storeOptions && storeOptions.length > 0 ? storeOptions : [ALL_STORES_LABEL]}
        onChange={onStoreChange}
      />
      <FilterDropdown
        label="Category"
        value={category}
        options={CATEGORY_OPTIONS}
        onChange={onCategoryChange}
      />
    </div>
  );
}
