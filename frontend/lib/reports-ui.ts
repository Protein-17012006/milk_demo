// Filter labels and helpers for the Dashboard page.
// Numbers come only from the live API (GET /kpi, /products, /reports/trends, /shelf-events). A value the backend
// cannot give stays null and the page shows "—" with the reason; nothing here is shelf data.

import { DEFAULT_DAYS, TIMEFRAMES } from "./shelf-ui";

export type TimeframeOption = string;
export type CategoryOption = "All Categories" | "Milk" | "Snacks";
export const TIMEFRAME_OPTIONS: TimeframeOption[] = TIMEFRAMES.map((t) => t.label);
export const DEFAULT_TIMEFRAME: TimeframeOption =
  TIMEFRAMES.find((t) => t.days === DEFAULT_DAYS)?.label ?? TIMEFRAME_OPTIONS[0];
export const CATEGORY_OPTIONS: CategoryOption[] = ["All Categories", "Milk", "Snacks"];
export const ALL_STORES_LABEL = "All Stores";

/** Days of a Timeframe label. */
export const daysOf = (label: TimeframeOption) => TIMEFRAMES.find((t) => t.label === label)?.days ?? DEFAULT_DAYS;

/** The SKU master category to send, or undefined for every category. */
export const categoryParam = (c: CategoryOption) => (c === "All Categories" ? undefined : c);

/** "DEMO-S01 — Demo Store S01" → "DEMO-S01"; the "All Stores (n)" label → undefined. */
export const storeParam = (label: string) => (label.startsWith(ALL_STORES_LABEL) ? undefined : label.split(" — ")[0]);
