"use client";

import React, { useEffect, useState } from "react";
import Image from "next/image";
import {
  Building2,
  Loader2,
  Lock,
  Upload,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { createApiClient, type ApiStore } from "@/lib/api";
import { parseImportFile } from "@/lib/import-parse";
import { imageTimeText } from "@/lib/model-status";
import { ShelfPlanSection } from "./ShelfPlanSection";

// Stores come only from the live API; signed out, the list stays empty rather than claiming a status.
const FALLBACK_STORES: ApiStore[] = [];

export function SettingsView() {
  const { user, isApproved, hasGroup, getIdToken } = useAuth();

  const [stores, setStores] = useState<ApiStore[]>(FALLBACK_STORES);
  const [timezoneLabel, setTimezoneLabel] = useState<string>(
    "Asia/Ho_Chi_Minh (UTC+7)"
  );
  // when the store list came back: "latest image at 15:45" is worked out against this, not while drawing
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const [liveSynced, setLiveSynced] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2600);
  };

  useEffect(() => {
    if (!isApproved) {
      setLiveSynced(false);
      setStores(FALLBACK_STORES);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const api = createApiClient(getIdToken);
    api
      .getSettings()
      .then((res) => {
        if (cancelled) return;
        setStores(res.stores.length > 0 ? res.stores : FALLBACK_STORES);
        setTimezoneLabel(res.timezone.value);
        setLiveSynced(true);
        // the settings answer lists the stores without their latest image: the store list has it
        return api.getStores().then((list) => {
          if (cancelled) return;
          setStores(list.items);
          setLoadedAt(new Date());
        });
      })
      .catch(() => {
        // fallback cleanly
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isApproved, getIdToken]);

  // Both catalogs are imported the same way: read the file into rows, send them, say how many went in.
  const importFile = async (
    e: React.ChangeEvent<HTMLInputElement>,
    send: (items: Record<string, unknown>[]) => Promise<void>,
    done: (count: number) => string
  ) => {
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;
    try {
      if (!isApproved || !hasGroup("team_admin")) {
        showToast("Your account cannot import files.");
        return;
      }
      const items = parseImportFile(file.name, await file.text());
      if (items.length === 0) {
        showToast("The file has no rows.");
        return;
      }
      await send(items);
      showToast(done(items.length));
    } catch (err) {
      showToast(err instanceof Error ? err.message : "The file could not be imported.");
    } finally {
      input.value = ""; // the same file can be chosen again after a fix
    }
  };

  const handleImportStoreFile = (e: React.ChangeEvent<HTMLInputElement>) =>
    importFile(
      e,
      async (items) => {
        const api = createApiClient(getIdToken);
        await api.importStoreList(items);
        setStores((await api.getStores()).items);
      },
      (n) => `Imported ${n} ${n === 1 ? "store" : "stores"}.`
    );

  const handleImportSkuFile = (e: React.ChangeEvent<HTMLInputElement>) =>
    importFile(
      e,
      async (items) => {
        await createApiClient(getIdToken).importSkuMaster(items);
      },
      (n) => `Imported ${n} ${n === 1 ? "product" : "products"} into the SKU master.`
    );

  return (
    <div className="min-h-full w-full bg-[#F7F8FA]">
      <div className="mx-auto w-full max-w-[980px] px-4 pt-[26px] pb-12 sm:px-6 lg:px-7">
        {/* Page Header */}
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-black/10 pb-[16px]">
          <div>
            <h1 className="text-[22px] font-normal leading-tight text-black">
              Settings
            </h1>
            <p className="mt-[4px] text-[12px] font-normal text-[#6B7280]">
              Your account, the stores and the shelf plan.
            </p>
          </div>
        </header>

        {loading && (
          <div className="mt-5 flex items-center gap-2 text-[13px] text-[#6B7280]">
            <Loader2 className="h-4 w-4 animate-spin text-[#EE730A]" />
            <span>Loading settings…</span>
          </div>
        )}

        <div className="mt-5 space-y-5">
          {/* Section 1: the account (read-only) */}
          <section className="rounded-[14px] border border-[#EFF0F6] bg-white p-6">
            <div className="flex flex-wrap items-center gap-4 border-b border-[#EFF0F6] pb-4">
              <div className="flex h-[48px] w-[48px] items-center justify-center rounded-[12px] border border-[#EFF0F6] bg-[#FAFAFA]">
                <Image
                  src="/images/logo-database.png"
                  alt="Workspace logo"
                  width={28}
                  height={28}
                  className="h-[28px] w-[28px] object-contain"
                />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-[15px] font-semibold text-[#111827]">
                  Account
                </h2>
              </div>
              <span className="inline-flex items-center gap-1 rounded-full bg-[#F3F4F6] px-2.5 py-1 text-[11px] font-medium text-[#4B5563]">
                <Lock className="h-3 w-3" />
                Read-only
              </span>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="text-[12px] font-medium text-[#6B7280]">
                  Email
                </p>
                <p className="mt-1 rounded-[8px] border border-[#EFF0F6] bg-[#F9FAFB] px-3 py-2 text-[13.5px] font-medium text-[#111827]">
                  {user?.email || "Not signed in"}
                </p>
              </div>
              <div>
                <p className="text-[12px] font-medium text-[#6B7280]">
                  Groups
                </p>
                <div className="mt-1 flex min-h-[38px] flex-wrap items-center gap-1.5 rounded-[8px] border border-[#EFF0F6] bg-[#F9FAFB] px-3 py-1.5">
                  {user && user.groups.length > 0 ? (
                    user.groups.map((grp) => (
                      <span
                        key={grp}
                        className="rounded-full bg-[#FFF7ED] px-2.5 py-0.5 text-[12px] font-semibold text-[#C2560A]"
                      >
                        {grp}
                      </span>
                    ))
                  ) : (
                    <span className="text-[13px] text-[#6B7280]">
                      {user ? "Waiting for approval" : "—"}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* The shelf plan per store (opening hours and expected SKUs) comes first: it is what an administrator
              opens Settings for, and the Dashboard's shelf numbers follow it */}
          {isApproved && liveSynced && (
            <ShelfPlanSection
              stores={stores}
              getIdToken={getIdToken}
              isAdmin={hasGroup("team_admin")}
              showToast={showToast}
            />
          )}

          {/* The stores (store list; an administrator imports the catalogs here) */}
          <section className="rounded-[14px] border border-[#EFF0F6] bg-white p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EFF0F6] pb-4">
              <div className="flex items-center gap-2.5">
                <Building2 className="h-[18px] w-[18px] text-[#EE730A]" />
                <div>
                  <h2 className="text-[15px] font-semibold text-[#111827]">
                    Monitored Stores ({stores.length})
                  </h2>
                  <p className="text-[12.5px] text-[#6B7280]">
                    The stores this site monitors.
                  </p>
                </div>
              </div>

              {hasGroup("team_admin") && (
                <div className="flex flex-wrap items-center gap-2">
                  <label
                    title="A .json or .csv file of stores"
                    className="inline-flex h-[34px] cursor-pointer items-center gap-1.5 rounded-[8px] border border-[#E5E7EB] bg-white px-3 text-[12.5px] font-medium text-[#111827] hover:bg-[#F9FAFB]"
                  >
                    <Upload className="h-3.5 w-3.5 text-[#EE730A]" />
                    <span>Import Store List</span>
                    <input
                      type="file"
                      accept=".json,.csv"
                      data-import="store-list"
                      onChange={(e) => void handleImportStoreFile(e)}
                      className="hidden"
                    />
                  </label>
                  <label
                    title="A .json or .csv file of products: SKU names, barcodes, pack sizes, categories"
                    className="inline-flex h-[34px] cursor-pointer items-center gap-1.5 rounded-[8px] border border-[#E5E7EB] bg-white px-3 text-[12.5px] font-medium text-[#111827] hover:bg-[#F9FAFB]"
                  >
                    <Upload className="h-3.5 w-3.5 text-[#EE730A]" />
                    <span>Import SKU Master</span>
                    <input
                      type="file"
                      accept=".json,.csv"
                      data-import="sku-master"
                      onChange={(e) => void handleImportSkuFile(e)}
                      className="hidden"
                    />
                  </label>
                </div>
              )}
            </div>

            <div className="mt-4 divide-y divide-[#EFF0F6]">
              {stores.length === 0 && !loading && (
                <p className="py-3 text-[12.5px] text-[#6B7280]">
                  {isApproved ? "No stores to show." : "The stores appear once your account is approved."}
                </p>
              )}
              {stores.map((st) => (
                <div
                  key={st.store_id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[12px] font-semibold text-[#EE730A]">
                        {st.store_id}
                      </span>
                      <span className="text-[13.5px] font-medium text-[#111827]">
                        {st.store_name}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[12px] text-[#6B7280]">
                      {st.district || "Ho Chi Minh City"} &middot; Camera:{" "}
                      <code>{st.camera_id || "CAM-S01-A"}</code>
                      {st.last_capture_timestamp && loadedAt && (
                        <> &middot; Latest image at {imageTimeText(st.last_capture_timestamp, loadedAt)}</>
                      )}
                    </p>
                  </div>

                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${
                      st.has_recent_capture
                        ? "bg-[#ECFDF5] text-[#047857]"
                        : "bg-[#F3F4F6] text-[#4B5563]"
                    }`}
                  >
                    {st.has_recent_capture ? "Active" : st.status || "Standby"}
                  </span>
                </div>
              ))}
            </div>
          </section>


          <p data-timezone-note className="px-1 text-[12px] text-[#6B7280]">
            Every time on this site and in the CSV files is in {timezoneLabel}.
          </p>
        </div>
      </div>

      {toastMsg && (
        <div className="fixed bottom-5 right-16 z-50 rounded-[10px] bg-[#111827] px-4 py-2.5 text-[12.5px] font-medium text-white shadow-lg">
          {toastMsg}
        </div>
      )}
    </div>
  );
}
