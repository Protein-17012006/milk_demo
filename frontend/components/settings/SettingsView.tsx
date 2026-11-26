"use client";

import React, { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import {
  Building2,
  Check,
  Clock,
  Loader2,
  Lock,
  ShieldCheck,
  Sliders,
  Upload,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { createApiClient, type ApiStore } from "@/lib/api";
import { parseImportFile } from "@/lib/import-parse";
import { ShelfPlanSection } from "./ShelfPlanSection";

const DATE_FORMATS = [
  "DD MMM YYYY, HH:mm",
  "DD/MM/YYYY HH:mm",
  "YYYY-MM-DD HH:mm",
] as const;

const LANDING_PAGES = ["Home", "Reports", "Products"] as const;

interface UserPreferences {
  date_format: string;
  default_landing: string;
}

const DEFAULT_PREFS: UserPreferences = {
  date_format: "DD MMM YYYY, HH:mm",
  default_landing: "Home",
};

// Stores come only from the live API; signed out, the list stays empty rather than claiming a status.
const FALLBACK_STORES: ApiStore[] = [];

export function SettingsView() {
  const { user, isApproved, hasGroup, getIdToken } = useAuth();

  const [savedPrefs, setSavedPrefs] = useState<UserPreferences>(DEFAULT_PREFS);
  const [draftPrefs, setDraftPrefs] = useState<UserPreferences>(DEFAULT_PREFS);
  const [stores, setStores] = useState<ApiStore[]>(FALLBACK_STORES);
  const [flagThreshold, setFlagThreshold] = useState<number>(0.7);
  const [timezoneLabel, setTimezoneLabel] = useState<string>(
    "Asia/Ho_Chi_Minh (UTC+7)"
  );
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
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
        setSavedPrefs(res.preferences);
        setDraftPrefs(res.preferences);
        setStores(res.stores.length > 0 ? res.stores : FALLBACK_STORES);
        setFlagThreshold(res.flag_threshold.value);
        setTimezoneLabel(res.timezone.value);
        setLiveSynced(true);
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

  const hasUnsavedChanges = useMemo(
    () =>
      draftPrefs.date_format !== savedPrefs.date_format ||
      draftPrefs.default_landing !== savedPrefs.default_landing,
    [draftPrefs, savedPrefs]
  );

  const handleSave = async () => {
    if (!isApproved) {
      setSavedPrefs(draftPrefs);
      showToast("Saved preferences locally (sign in to persist to AWS)");
      return;
    }
    setSaving(true);
    try {
      const api = createApiClient(getIdToken);
      await api.updateSettings(draftPrefs);
      setSavedPrefs(draftPrefs);
      showToast("Preferences saved to AWS DynamoDB (user_prefs)");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

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
              {liveSynced
                ? "Synced with AWS Cognito & DynamoDB (Phase 1 configuration)"
                : "Account identity, user preferences, inference rules, and store directory"}
            </p>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={!hasUnsavedChanges || saving}
            className={`flex h-[36px] items-center gap-[6px] rounded-[8px] px-[16px] text-[13px] font-semibold transition-colors ${
              hasUnsavedChanges && !saving
                ? "bg-[#EE730A] text-white hover:bg-[#D96504] cursor-pointer"
                : "bg-[#EE730A]/45 text-white/90 cursor-not-allowed"
            }`}
          >
            {saving ? (
              <Loader2 className="h-[15px] w-[15px] animate-spin" />
            ) : (
              <Check className="h-[15px] w-[15px]" strokeWidth={2.2} />
            )}
            <span>{saving ? "Saving..." : "Save Preferences"}</span>
          </button>
        </header>

        {loading && (
          <div className="mt-5 flex items-center gap-2 text-[13px] text-[#6B7280]">
            <Loader2 className="h-4 w-4 animate-spin text-[#EE730A]" />
            <span>Loading settings from AWS...</span>
          </div>
        )}

        <div className="mt-5 space-y-5">
          {/* Section 1: Account & Cognito Groups (Read-only) */}
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
                  Account &amp; Cognito Role
                </h2>
                <p className="mt-0.5 text-[12.5px] text-[#6B7280]">
                  Managed centrally via Amazon Cognito User Pool + TOTP MFA
                  (single client: Datagent).
                </p>
              </div>
              <span className="inline-flex items-center gap-1 rounded-full bg-[#F3F4F6] px-2.5 py-1 text-[11px] font-medium text-[#4B5563]">
                <Lock className="h-3 w-3" />
                Read-only
              </span>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="text-[12px] font-medium text-[#6B7280]">
                  Cognito Email
                </p>
                <p className="mt-1 rounded-[8px] border border-[#EFF0F6] bg-[#F9FAFB] px-3 py-2 text-[13.5px] font-medium text-[#111827]">
                  {user?.email || "Not signed in"}
                </p>
              </div>
              <div>
                <p className="text-[12px] font-medium text-[#6B7280]">
                  Assigned Cognito Groups
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
                      {user ? "Pending team_admin assignment" : "—"}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* Section 2: User Preferences (Editable -> DynamoDB user_prefs) */}
          <section className="rounded-[14px] border border-[#EFF0F6] bg-white p-6">
            <div className="flex items-center gap-2.5 border-b border-[#EFF0F6] pb-4">
              <Sliders className="h-[18px] w-[18px] text-[#EE730A]" />
              <div>
                <h2 className="text-[15px] font-semibold text-[#111827]">
                  Personal Display Preferences
                </h2>
                <p className="text-[12.5px] text-[#6B7280]">
                  Saved per user in DynamoDB (<code>user_prefs</code>).
                </p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="pref-date-format"
                  className="block text-[12px] font-medium text-[#374151]"
                >
                  Date Format
                </label>
                <select
                  id="pref-date-format"
                  value={draftPrefs.date_format}
                  onChange={(e) =>
                    setDraftPrefs((prev) => ({
                      ...prev,
                      date_format: e.target.value,
                    }))
                  }
                  className="mt-1.5 h-[38px] w-full rounded-[8px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] outline-none focus:border-[#EE730A]"
                >
                  {DATE_FORMATS.map((fmt) => (
                    <option key={fmt} value={fmt}>
                      {fmt}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor="pref-landing"
                  className="block text-[12px] font-medium text-[#374151]"
                >
                  Default Landing Page
                </label>
                <select
                  id="pref-landing"
                  value={draftPrefs.default_landing}
                  onChange={(e) =>
                    setDraftPrefs((prev) => ({
                      ...prev,
                      default_landing: e.target.value,
                    }))
                  }
                  className="mt-1.5 h-[38px] w-full rounded-[8px] border border-[#D1D5DB] bg-white px-3 text-[13px] text-[#111827] outline-none focus:border-[#EE730A]"
                >
                  {LANDING_PAGES.map((page) => (
                    <option key={page} value={page}>
                      {page}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          {/* Sections 3 & 4: Timezone & Flag Threshold (Read-only system policy) */}
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <section className="rounded-[14px] border border-[#EFF0F6] bg-white p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-[#EE730A]" />
                  <h2 className="text-[14px] font-semibold text-[#111827]">
                    Timezone
                  </h2>
                </div>
                <span className="text-[11px] font-medium text-[#6B7280]">
                  Read-only
                </span>
              </div>
              <p className="mt-3 rounded-[8px] border border-[#EFF0F6] bg-[#F9FAFB] px-3 py-2 text-[13.5px] font-medium text-[#111827]">
                {timezoneLabel}
              </p>
              <p className="mt-2 text-[11.5px] text-[#6B7280]">
                Standard ISO 8601 UTC+7 across all captures and CSV exports (Data
                Dictionary).
              </p>
            </section>

            <section className="rounded-[14px] border border-[#EFF0F6] bg-white p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-[#EE730A]" />
                  <h2 className="text-[14px] font-semibold text-[#111827]">
                    Low-Confidence Flag Threshold
                  </h2>
                </div>
                <span className="text-[11px] font-medium text-[#6B7280]">
                  Read-only
                </span>
              </div>
              <p className="mt-3 rounded-[8px] border border-[#EFF0F6] bg-[#F9FAFB] px-3 py-2 font-mono text-[14px] font-semibold text-[#111827]">
                {flagThreshold.toFixed(2)} (MILK_FLAG_THRESHOLD)
              </p>
              <p className="mt-2 text-[11.5px] text-[#6B7280]">
                Rows below 0.70 raw average confidence or with{" "}
                <code>sku_id = NULL</code> are flagged for review.
              </p>
            </section>
          </div>

          {/* Section 5: Store Directory (store_list + team_admin import) */}
          <section className="rounded-[14px] border border-[#EFF0F6] bg-white p-6">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#EFF0F6] pb-4">
              <div className="flex items-center gap-2.5">
                <Building2 className="h-[18px] w-[18px] text-[#EE730A]" />
                <div>
                  <h2 className="text-[15px] font-semibold text-[#111827]">
                    Monitored Stores ({stores.length})
                  </h2>
                  <p className="text-[12.5px] text-[#6B7280]">
                    Loaded from <code>store_list</code>; <code>team_admin</code>{" "}
                    can import updated store JSON files.
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
              {stores.length === 0 && (
                <p className="py-3 text-[12.5px] text-[#6B7280]">
                  Sign in with an approved account to load the store list.
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
                      {st.last_capture_timestamp && (
                        <> &middot; Last capture: {st.last_capture_timestamp}</>
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

          {/* Section 6: Shelf plan per store (opening hours + expected SKUs) for the Dashboard's shelf numbers */}
          {isApproved && liveSynced && (
            <ShelfPlanSection
              stores={stores}
              getIdToken={getIdToken}
              isAdmin={hasGroup("team_admin")}
              showToast={showToast}
            />
          )}
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
