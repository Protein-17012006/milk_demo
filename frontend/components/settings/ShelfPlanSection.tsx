"use client";

import React, { useEffect, useMemo, useState } from "react";
import { ApiError, createApiClient, type ApiProduct, type ApiShelfPlan, type ApiStore } from "@/lib/api";

type Client = ReturnType<typeof createApiClient>;

const ERRORS: Record<string, string> = {
  INVALID_HOURS: "Opening hours must be HH:MM, with closing after opening.",
  UNKNOWN_SKU: "One of the chosen SKUs is not in the SKU Master.",
  INVALID_SKUS: "The SKU list could not be read.",
  FORBIDDEN: "Only an administrator can change the shelf plan.",
};

function StorePlan({
  store,
  products,
  api,
  isAdmin,
  showToast,
}: {
  store: ApiStore;
  products: ApiProduct[];
  api: Client;
  isAdmin: boolean;
  showToast: (msg: string) => void;
}) {
  const [plan, setPlan] = useState<ApiShelfPlan | null>(null);
  const [openTime, setOpenTime] = useState("");
  const [closeTime, setCloseTime] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [saving, setSaving] = useState(false);

  const adopt = (p: ApiShelfPlan) => {
    setPlan(p);
    setOpenTime(p.open_time ?? "");
    setCloseTime(p.close_time ?? "");
    setSelected(new Set(p.expected_skus));
  };

  useEffect(() => {
    let cancelled = false;
    api
      .getShelfPlan(store.store_id)
      .then((p) => {
        if (!cancelled) adopt(p);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [api, store.store_id]);

  const suggested = useMemo(() => new Set(plan?.suggested.map((s) => s.sku_id) ?? []), [plan]);
  const groups = useMemo(() => {
    const byLine = new Map<string, ApiProduct[]>();
    for (const p of products) {
      const line = `${p.brand ?? "Other"} · ${p.subcategory ?? p.category ?? "Other"}`;
      byLine.set(line, [...(byLine.get(line) ?? []), p]);
    }
    return [...byLine.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [products]);

  const toggle = (sku: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sku)) next.delete(sku);
      else next.add(sku);
      return next;
    });

  const save = async () => {
    setSaving(true);
    try {
      adopt(await api.saveShelfPlan(store.store_id, { open_time: openTime, close_time: closeTime, expected_skus: [...selected] }));
      showToast("Saved. The last 15 days are recomputed within 5 minutes.");
    } catch (err) {
      showToast(err instanceof ApiError ? (ERRORS[err.code] ?? err.message) : "Could not save the shelf plan.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section data-shelf-plan={store.store_id} className="rounded-[14px] border border-[#EFF0F6] bg-white p-6">
      <h2 className="text-[15px] font-semibold text-[#111827]">Shelf plan for {store.store_name}</h2>
      <p className="mt-1 max-w-[78ch] text-[12.5px] leading-[1.5] text-[#6B7280]">
        Opening hours and the SKUs this store should have on the shelf. The Dashboard counts on-shelf availability,
        out-of-stock and restocks only inside these hours and only for these SKUs.
      </p>
      <p data-shelf-plan-source className="mt-2 text-[12px] text-[#374151]">
        {plan === null
          ? "Loading…"
          : plan.source === "suggested"
            ? "Automatic until an administrator saves this list: the SKUs seen clearly in the last 7 days."
            : `Saved by ${plan.updated_by ?? "—"} on ${plan.updated_at?.slice(0, 16).replace("T", " ") ?? "—"}.`}
        {plan && !plan.open_time && " Opening hours are not set, so shelf numbers are off for this store."}
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-[12px] text-[#6B7280]">
          Opens (UTC+7)
          <input
            type="time"
            aria-label="Opens"
            value={openTime}
            disabled={!isAdmin}
            onChange={(e) => setOpenTime(e.target.value)}
            className="h-[34px] rounded-[7px] border border-[#D1D5DB] bg-white px-2.5 text-[13px] text-[#111827] disabled:bg-[#F9FAFB]"
          />
        </label>
        <label className="flex flex-col gap-1 text-[12px] text-[#6B7280]">
          Closes (UTC+7)
          <input
            type="time"
            aria-label="Closes"
            value={closeTime}
            disabled={!isAdmin}
            onChange={(e) => setCloseTime(e.target.value)}
            className="h-[34px] rounded-[7px] border border-[#D1D5DB] bg-white px-2.5 text-[13px] text-[#111827] disabled:bg-[#F9FAFB]"
          />
        </label>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        {groups.map(([line, skus]) => (
          <fieldset key={line} className="rounded-[10px] border border-[#EFF0F6] p-3">
            <legend className="px-1 text-[12.5px] font-semibold text-[#374151]">{line}</legend>
            {skus.map((p) => (
              <label key={p.sku_id} className="flex items-start gap-2 py-1 text-[12.5px] text-[#111827]">
                <input
                  type="checkbox"
                  data-sku={p.sku_id}
                  checked={selected.has(p.sku_id)}
                  disabled={!isAdmin}
                  onChange={() => toggle(p.sku_id)}
                  className="mt-[3px]"
                />
                <span>
                  {p.sku_name}
                  {suggested.has(p.sku_id) && (
                    <span className="ml-2 rounded-full bg-[#ECFDF5] px-2 py-0.5 text-[10.5px] font-medium text-[#047857]">
                      Seen in the last 7 days
                    </span>
                  )}
                </span>
              </label>
            ))}
          </fieldset>
        ))}
      </div>

      {isAdmin ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setSelected(new Set(suggested))}
            className="rounded-[8px] border border-[#E5E7EB] bg-white px-3 py-1.5 text-[13px] font-medium text-[#111827] hover:bg-[#F9FAFB] cursor-pointer"
          >
            Use suggestion
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void save()}
            className="rounded-[8px] bg-[#EE730A] px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-[#D96504] disabled:opacity-50 cursor-pointer"
          >
            Save shelf plan
          </button>
        </div>
      ) : (
        <p className="mt-4 text-[12px] text-[#6B7280]">Only an administrator can change the shelf plan.</p>
      )}
    </section>
  );
}

/** Settings: each store's opening hours and expected SKUs, which the Dashboard's shelf numbers depend on. */
export function ShelfPlanSection({
  stores,
  getIdToken,
  isAdmin,
  showToast,
}: {
  stores: ApiStore[];
  getIdToken: Parameters<typeof createApiClient>[0];
  isAdmin: boolean;
  showToast: (msg: string) => void;
}) {
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);
  const [products, setProducts] = useState<ApiProduct[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .getProducts()
      .then((res) => {
        if (!cancelled) setProducts(res.items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [api]);

  return (
    <>
      {stores.map((store) => (
        <StorePlan key={store.store_id} store={store} products={products} api={api} isAdmin={isAdmin} showToast={showToast} />
      ))}
    </>
  );
}
