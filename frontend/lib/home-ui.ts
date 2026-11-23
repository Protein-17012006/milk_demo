// Types and navigation entries for the Home page search.
// Product suggestions come from the live API (GET /products); this file holds no shelf data.

export interface HomeSearchProduct {
  id: string;
  name: string;
  sku: string;
  manufacturer: string;
  category: string;
  packType: "bottle" | "box";
  units: number;
  storesActive: number;
  storesTotal: number;
}

export interface HomeSearchPageItem {
  id: string;
  title: string;
  subtitle: string;
  href: string;
}

export interface RecentPageItem {
  id: string;
  label: string;
  href: string;
}

/** Pages offered by the search box. */
export const HOME_SEARCH_PAGES: HomeSearchPageItem[] = [
  {
    id: "page-dashboard",
    title: "Dashboard · Reports",
    subtitle: "KPIs, stock count & audit insights",
    href: "/dashboard",
  },
  {
    id: "page-category",
    title: "Category · Products SKU List",
    subtitle: "Browse all monitored SKUs & shelves",
    href: "/category",
  },
  {
    id: "page-settings",
    title: "Settings · Workspace Preferences",
    subtitle: "Account, stores & inference config",
    href: "/settings",
  },
];

/** Shortcuts shown in the left "Recents" column. */
export const DEFAULT_RECENT_PAGES: RecentPageItem[] = [
  { id: "rec-dashboard", label: "Dashboard", href: "/dashboard" },
  { id: "rec-category", label: "Category", href: "/category" },
  { id: "rec-home", label: "Home", href: "/" },
  { id: "rec-settings", label: "Settings", href: "/settings" },
];
