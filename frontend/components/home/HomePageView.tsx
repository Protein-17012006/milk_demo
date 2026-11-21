"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Search,
  History,
  ChevronRight,
  List,
  X,
} from "lucide-react";
import {
  DEFAULT_RECENT_PAGES,
  HOME_SEARCH_PAGES,
  HOME_SEARCH_PRODUCTS,
  type HomeSearchPageItem,
  type HomeSearchProduct,
} from "@/data/home-mock";
import { useAuth } from "@/lib/auth";
import { createApiClient } from "@/lib/api";

function PackBoxIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 22 22"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M7.33333 2.29169H14.6667L16.5 5.95835H5.5L7.33333 2.29169Z"
        fill="#2F6FD6"
      />
      <path
        d="M15.4 5.95831H6.6C5.99249 5.95831 5.5 6.4508 5.5 7.05831V18.6083C5.5 19.2158 5.99249 19.7083 6.6 19.7083H15.4C16.0075 19.7083 16.5 19.2158 16.5 18.6083V7.05831C16.5 6.4508 16.0075 5.95831 15.4 5.95831Z"
        fill="#2F6FD6"
      />
      <path
        d="M13.2917 10.0833H8.70841C8.20215 10.0833 7.79175 10.4937 7.79175 11V14.6666C7.79175 15.1729 8.20215 15.5833 8.70841 15.5833H13.2917C13.798 15.5833 14.2084 15.1729 14.2084 14.6666V11C14.2084 10.4937 13.798 10.0833 13.2917 10.0833Z"
        fill="white"
      />
    </svg>
  );
}

function PackBottleIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 22 22"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M12.3749 1.83331H9.62492C9.11866 1.83331 8.70825 2.24372 8.70825 2.74998V3.66665C8.70825 4.17291 9.11866 4.58331 9.62492 4.58331H12.3749C12.8812 4.58331 13.2916 4.17291 13.2916 3.66665V2.74998C13.2916 2.24372 12.8812 1.83331 12.3749 1.83331Z"
        fill="#D6336C"
      />
      <path
        d="M8.25 4.58331H13.75V5.95831C15.4 6.87498 16.5 8.52498 16.5 10.5416V18.3333C16.5 18.8195 16.3068 19.2859 15.963 19.6297C15.6192 19.9735 15.1529 20.1666 14.6667 20.1666H7.33333C6.8471 20.1666 6.38079 19.9735 6.03697 19.6297C5.69315 19.2859 5.5 18.8195 5.5 18.3333V10.5416C5.5 8.52498 6.6 6.87498 8.25 5.95831V4.58331Z"
        fill="#D6336C"
      />
      <path
        d="M13.2917 11H8.70841C8.20215 11 7.79175 11.4104 7.79175 11.9167V14.6667C7.79175 15.1729 8.20215 15.5833 8.70841 15.5833H13.2917C13.798 15.5833 14.2084 15.1729 14.2084 14.6667V11.9167C14.2084 11.4104 13.798 11 13.2917 11Z"
        fill="white"
      />
    </svg>
  );
}

type FlatSearchItem =
  | { kind: "product"; data: HomeSearchProduct }
  | { kind: "page"; data: HomeSearchPageItem };

export function HomePageView() {
  const router = useRouter();
  const { user, isApproved, getIdToken } = useAuth();
  const [query, setQuery] = useState("");
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [liveProducts, setLiveProducts] = useState<HomeSearchProduct[] | null>(
    null
  );
  const [recentProducts, setRecentProducts] = useState<HomeSearchProduct[]>([]);
  const [selectedProduct, setSelectedProduct] =
    useState<HomeSearchProduct | null>(null);

  const searchContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load real SKU catalog from AWS when authenticated & approved
  useEffect(() => {
    if (!isApproved) {
      setLiveProducts(null);
      return;
    }
    let cancelled = false;
    const api = createApiClient(getIdToken);
    api
      .getProducts()
      .then((res) => {
        if (cancelled) return;
        setLiveProducts(
          res.items.map((p) => ({
            id: p.sku_id,
            name: p.sku_name,
            sku: p.model_alias || p.sku_id,
            manufacturer: p.manufacturer || p.brand || "Unassigned",
            category: p.category || "Milk",
            packType: (p.pack_type || "").toLowerCase().includes("bottle")
              ? "bottle"
              : "box",
            units: p.unit_count,
            storesActive: p.stores_available,
            storesTotal: p.stores_total,
          }))
        );
      })
      .catch(() => {
        // fallback silently to sample catalog
      });
    return () => {
      cancelled = true;
    };
  }, [isApproved, getIdToken]);

  const catalogProducts = liveProducts ?? HOME_SEARCH_PRODUCTS;

  // Filter products & pages based on query; default matches exact Figma suggestions
  const { visibleProducts, visiblePages, totalResultCount } = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return {
        visibleProducts: catalogProducts.slice(0, 3),
        visiblePages: HOME_SEARCH_PAGES.slice(0, 1),
        totalResultCount: catalogProducts.length + HOME_SEARCH_PAGES.length,
      };
    }

    const matchedProducts = catalogProducts.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.sku.toLowerCase().includes(q) ||
        p.manufacturer.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q)
    );

    const matchedPages = HOME_SEARCH_PAGES.filter(
      (pg) =>
        pg.title.toLowerCase().includes(q) ||
        pg.subtitle.toLowerCase().includes(q)
    );

    return {
      visibleProducts: matchedProducts.slice(0, 4),
      visiblePages: matchedPages.slice(0, 3),
      totalResultCount: matchedProducts.length + matchedPages.length,
    };
  }, [query, catalogProducts]);

  const flatItems: FlatSearchItem[] = useMemo(
    () => [
      ...visibleProducts.map((data) => ({ kind: "product" as const, data })),
      ...visiblePages.map((data) => ({ kind: "page" as const, data })),
    ],
    [visibleProducts, visiblePages]
  );

  const clampedActiveIndex =
    flatItems.length === 0 ? -1 : Math.min(activeIndex, flatItems.length - 1);

  // Global Ctrl+K / Cmd+K shortcut
  useEffect(() => {
    function handleGlobalKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setSuggestionsOpen(true);
        setActiveIndex(0);
      }
    }
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  // Close suggestions on outside click
  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setSuggestionsOpen(false);
      }
    }
    if (suggestionsOpen) {
      document.addEventListener("mousedown", handleOutsideClick);
    }
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [suggestionsOpen]);

  const handleOpenItem = (item: FlatSearchItem) => {
    setSuggestionsOpen(false);
    if (item.kind === "page") {
      router.push(item.data.href);
      return;
    }
    setSelectedProduct(item.data);
    setRecentProducts((prev) => [
      item.data,
      ...prev.filter((p) => p.id !== item.data.id).slice(0, 4),
    ]);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setSuggestionsOpen(false);
      inputRef.current?.blur();
      return;
    }

    if (!suggestionsOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        setSuggestionsOpen(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (flatItems.length > 0) {
        setActiveIndex((prev) => (prev + 1) % flatItems.length);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (flatItems.length > 0) {
        setActiveIndex(
          (prev) => (prev - 1 + flatItems.length) % flatItems.length
        );
      }
    } else if (e.key === "Enter" && clampedActiveIndex >= 0) {
      e.preventDefault();
      handleOpenItem(flatItems[clampedActiveIndex]);
    }
  };

  return (
    <div className="flex min-h-full w-full flex-col items-center px-5 pt-[120px] pb-16 lg:pt-[200px]">
      {/* Hero Heading & Status Line */}
      <div className="flex flex-col items-center text-center">
        <h1 className="text-[30px] leading-tight tracking-[-0.015em] text-black sm:text-[40px]">
          <span className="font-normal">Let&rsquo;s back to work </span>
          <span className="font-medium">
            {user?.email ? user.email.split("@")[0] : "Datagent"}
          </span>
          <span className="font-normal">!</span>
        </h1>
        <p className="mt-[10px] text-[13px] font-normal text-black/60">
          {liveProducts
            ? `Connected to live AWS Singapore backend · ${liveProducts.length} SKUs synced (UTC+7)`
            : "Look back your previous work · Sign in to sync live shelf data (UTC+7)"}
        </p>
      </div>

      {/* Centered Search Bar + Suggestions Dropdown */}
      <div
        ref={searchContainerRef}
        className="relative mt-[28px] w-full max-w-[720px]"
      >
        <div
          onClick={() => {
            inputRef.current?.focus();
            setSuggestionsOpen(true);
          }}
          className={`flex h-[60px] w-full items-center gap-[14px] rounded-full bg-[#F7F7F7] pl-[20px] pr-[16px] shadow-[0_4px_16px_rgba(0,0,0,0.05)] transition-colors ${
            suggestionsOpen
              ? "border border-black/60"
              : "border border-black/20 hover:border-black/35"
          }`}
        >
          <Search
            className="h-[22px] w-[22px] shrink-0 text-black/70"
            strokeWidth={1.75}
          />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onFocus={() => {
              setSuggestionsOpen(true);
              setActiveIndex(0);
            }}
            onChange={(e) => {
              setQuery(e.target.value);
              setSuggestionsOpen(true);
              setActiveIndex(0);
            }}
            onKeyDown={handleInputKeyDown}
            placeholder="Search products, pages, and features..."
            aria-label="Search products, pages, and features"
            aria-expanded={suggestionsOpen}
            aria-controls="home-search-suggestions"
            role="combobox"
            aria-autocomplete="list"
            className="min-w-0 flex-1 bg-transparent text-[16px] font-light text-black placeholder:text-black/70 outline-none"
          />
          <kbd className="shrink-0 rounded-[3px] border border-black/30 bg-[#E5E5E5] px-[6px] py-[2px] font-sans text-[10px] font-normal text-black/70">
            Ctrl K
          </kbd>
        </div>

        {/* Search Suggestions Popover — matches Figma #201:736 */}
        {suggestionsOpen && (
          <div
            id="home-search-suggestions"
            role="listbox"
            className="absolute left-0 right-0 top-[67px] z-30 overflow-hidden rounded-[10px] border border-black/[0.12] bg-white pt-[8px] shadow-[0_10px_28px_rgba(0,0,0,0.12)]"
          >
            <div className="px-[8px] pb-[4px]">
              {flatItems.length === 0 ? (
                <div className="px-3 py-6 text-center text-[13px] text-black/50">
                  No matching products or pages for &ldquo;{query}&rdquo;
                </div>
              ) : (
                <>
                  {/* Products Group */}
                  {visibleProducts.length > 0 && (
                    <div>
                      <div className="px-[10px] pt-[6px] pb-[4px] text-[12px] font-medium text-black/55">
                        Products
                      </div>
                      <div className="flex flex-col gap-[2px]">
                        {visibleProducts.map((product, idx) => {
                          const isActive = clampedActiveIndex === idx;
                          return (
                            <button
                              key={product.id}
                              type="button"
                              role="option"
                              aria-selected={isActive}
                              onMouseEnter={() => setActiveIndex(idx)}
                              onClick={() =>
                                handleOpenItem({ kind: "product", data: product })
                              }
                              className={`flex w-full items-center gap-[12px] rounded-[8px] px-[10px] py-[8px] pr-[12px] text-left transition-colors cursor-pointer ${
                                isActive ? "bg-[#F3F4F6]" : "bg-transparent hover:bg-[#F9FAFB]"
                              }`}
                            >
                              <span
                                className={`flex h-[36px] w-[36px] shrink-0 items-center justify-center rounded-[8px] ${
                                  product.packType === "bottle"
                                    ? "bg-[#FDEDF3]"
                                    : "bg-[#E8F1FD]"
                                }`}
                              >
                                {product.packType === "bottle" ? (
                                  <PackBottleIcon />
                                ) : (
                                  <PackBoxIcon />
                                )}
                              </span>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-[13px] font-medium leading-[1.3] text-black">
                                  {product.name}
                                </p>
                                <p className="mt-[2px] truncate text-[12px] font-normal leading-[1.3] text-black/60">
                                  {product.sku} &middot; {product.units} units &middot;{" "}
                                  {product.storesActive}/{product.storesTotal} stores
                                </p>
                              </div>
                              {isActive && (
                                <span className="shrink-0 text-[11px] font-medium text-black/45">
                                  &crarr; Open
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Pages Group */}
                  {visiblePages.length > 0 && (
                    <div className={visibleProducts.length > 0 ? "mt-[4px]" : ""}>
                      <div className="px-[10px] pt-[8px] pb-[4px] text-[12px] font-medium text-black/55">
                        Pages
                      </div>
                      <div className="flex flex-col gap-[2px]">
                        {visiblePages.map((pageItem, pIdx) => {
                          const flatIdx = visibleProducts.length + pIdx;
                          const isActive = clampedActiveIndex === flatIdx;
                          return (
                            <button
                              key={pageItem.id}
                              type="button"
                              role="option"
                              aria-selected={isActive}
                              onMouseEnter={() => setActiveIndex(flatIdx)}
                              onClick={() =>
                                handleOpenItem({ kind: "page", data: pageItem })
                              }
                              className={`flex w-full items-center gap-[12px] rounded-[8px] px-[10px] py-[8px] pr-[12px] text-left transition-colors cursor-pointer ${
                                isActive ? "bg-[#F3F4F6]" : "bg-transparent hover:bg-[#F9FAFB]"
                              }`}
                            >
                              <span className="flex h-[36px] w-[36px] shrink-0 items-center justify-center rounded-[8px] bg-[#F3F4F6] text-[#374151]">
                                <List className="h-[18px] w-[18px]" strokeWidth={1.75} />
                              </span>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-[13px] font-medium leading-[1.3] text-black">
                                  {pageItem.title}
                                </p>
                                <p className="mt-[2px] truncate text-[12px] font-normal leading-[1.3] text-black/60">
                                  {pageItem.subtitle}
                                </p>
                              </div>
                              {isActive && (
                                <span className="shrink-0 text-[11px] font-medium text-black/45">
                                  &crarr; Open
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Suggestions Footer */}
            <div className="mt-[4px] flex items-center justify-between border-t border-black/[0.08] px-[14px] py-[10px]">
              <span className="text-[11px] font-normal text-black/50">
                &uarr;&darr; to move &middot; &crarr; to open &middot; Esc to close
              </span>
              <button
                type="button"
                onClick={() => {
                  setSuggestionsOpen(false);
                  router.push("/category");
                }}
                className="text-[12px] font-medium text-[#C2560A] hover:underline cursor-pointer"
              >
                See all {totalResultCount} results
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Recents 2-Column Grid — matches Figma #138:2163 */}
      <section
        aria-label="Recent items"
        className="mt-[56px] grid w-full max-w-[720px] grid-cols-1 gap-x-[12px] gap-y-8 md:grid-cols-2"
      >
        {/* Left Recents Column (Recently visited pages) */}
        <div className="flex flex-col">
          <div className="flex items-center justify-between pb-[12px]">
            <h2 className="text-[12px] font-medium text-black/60">Recents</h2>
            <button
              type="button"
              aria-label="Recent pages options"
              className="rounded-[6px] px-[6px] py-[3px] text-[11px] font-medium leading-none text-[#374151] hover:bg-black/[0.05] transition-colors cursor-pointer"
            >
              ...
            </button>
          </div>

          <div className="max-h-[168px] overflow-y-auto pr-1">
            {DEFAULT_RECENT_PAGES.map((item) => (
              <Link
                key={item.id}
                href={item.href}
                className="group flex h-[47px] items-center justify-between border-b border-black/40 px-[2px] transition-colors hover:bg-black/[0.02]"
              >
                <span className="flex items-center gap-[13px]">
                  <History
                    className="h-[14px] w-[14px] shrink-0 text-black/70"
                    strokeWidth={1.75}
                  />
                  <span className="text-[12px] font-medium text-black/70 group-hover:text-black">
                    {item.label}
                  </span>
                </span>
                <ChevronRight
                  className="h-[14px] w-[14px] shrink-0 text-black/60 transition-transform group-hover:translate-x-0.5 group-hover:text-black"
                  strokeWidth={1.8}
                />
              </Link>
            ))}
          </div>
        </div>

        {/* Right Recents Column (Matches Figma clean column; fills as products are opened) */}
        <div className="flex flex-col">
          <div className="flex items-center justify-between pb-[12px]">
            <h2 className="text-[12px] font-medium text-black/60">Recents</h2>
            <button
              type="button"
              onClick={() => setRecentProducts([])}
              title={
                recentProducts.length > 0
                  ? "Clear recent products"
                  : "Recent items options"
              }
              aria-label="Recent items options"
              className="rounded-[6px] px-[6px] py-[3px] text-[11px] font-medium leading-none text-[#374151] hover:bg-black/[0.05] transition-colors cursor-pointer"
            >
              ...
            </button>
          </div>

          <div className="max-h-[168px] overflow-y-auto pr-1">
            {recentProducts.map((product) => (
              <button
                key={product.id}
                type="button"
                onClick={() => setSelectedProduct(product)}
                className="group flex h-[47px] w-full items-center justify-between border-b border-black/40 px-[2px] text-left transition-colors hover:bg-black/[0.02] cursor-pointer"
              >
                <span className="flex min-w-0 items-center gap-[13px]">
                  <History
                    className="h-[14px] w-[14px] shrink-0 text-black/70"
                    strokeWidth={1.75}
                  />
                  <span className="truncate text-[12px] font-medium text-black/70 group-hover:text-black">
                    {product.name}
                  </span>
                </span>
                <ChevronRight
                  className="ml-2 h-[14px] w-[14px] shrink-0 text-black/60 transition-transform group-hover:translate-x-0.5 group-hover:text-black"
                  strokeWidth={1.8}
                />
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Quick Product Preview Modal when opening a search result */}
      {selectedProduct && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 p-4 backdrop-blur-[1px]"
          onClick={() => setSelectedProduct(null)}
        >
          <div
            className="w-full max-w-[460px] rounded-[14px] border border-[#E5E7EB] bg-white p-5 shadow-[0_10px_28px_rgba(0,0,0,0.12)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] ${
                    selectedProduct.packType === "bottle"
                      ? "bg-[#FDEDF3]"
                      : "bg-[#E8F1FD]"
                  }`}
                >
                  {selectedProduct.packType === "bottle" ? (
                    <PackBottleIcon />
                  ) : (
                    <PackBoxIcon />
                  )}
                </span>
                <div>
                  <h3 className="text-[14px] font-semibold text-black">
                    {selectedProduct.name}
                  </h3>
                  <p className="text-[12px] text-black/60">
                    {selectedProduct.sku} &middot; {selectedProduct.manufacturer}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedProduct(null)}
                aria-label="Close product preview"
                className="flex h-7 w-7 items-center justify-center rounded-full text-black/55 hover:bg-black/[0.05] hover:text-black cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 grid grid-cols-3 gap-2.5">
              <div className="rounded-[10px] border border-[#EFF0F6] bg-[#FAFAFA] p-3">
                <p className="text-[11px] text-black/55">On-Shelf Units</p>
                <p className="mt-1 text-[16px] font-semibold text-black">
                  {selectedProduct.units}
                </p>
              </div>
              <div className="rounded-[10px] border border-[#EFF0F6] bg-[#FAFAFA] p-3">
                <p className="text-[11px] text-black/55">Store Presence</p>
                <p className="mt-1 text-[16px] font-semibold text-black">
                  {selectedProduct.storesActive}/{selectedProduct.storesTotal}
                </p>
              </div>
              <div className="rounded-[10px] border border-[#EFF0F6] bg-[#FAFAFA] p-3">
                <p className="text-[11px] text-black/55">Category</p>
                <p className="mt-1 truncate text-[13px] font-semibold text-black">
                  {selectedProduct.category}
                </p>
              </div>
            </div>

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSelectedProduct(null)}
                className="rounded-[8px] border border-[#EFF0F6] px-3.5 py-1.5 text-[12px] font-medium text-black/70 hover:bg-[#F7F7F7] cursor-pointer"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectedProduct(null);
                  router.push("/dashboard");
                }}
                className="rounded-[8px] bg-[#EE730A] px-3.5 py-1.5 text-[12px] font-medium text-white hover:bg-[#D96504] cursor-pointer"
              >
                View in Reports
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
