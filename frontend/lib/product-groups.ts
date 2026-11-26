// Groups the Products rows by brand + product line (subcategory from the SKU Master).
// Display only: every group number is a sum or maximum of per-SKU API values; sku_id stays the unit.
// Imports are type-only so Node can run the unit tests without the Next.js path aliases.
import type { PrimaryCategory, SkuProduct, SortOption } from "./products-ui";

export interface ProductGroup {
  key: string;
  label: string;
  primaryCategory: PrimaryCategory;
  thumbnail: string;
  variants: SkuProduct[];
  totalUnits: number;
  variantsOnShelf: number;
  flaggedCount: number;
  /** Unit-weighted average over variants with units; null when no variant is on the shelf. */
  confidence: number | null;
  packLabel: string;
  storesAvailable: number;
  storesTotal: number;
}

/** Stable across refreshes, so the page can remember which groups are open. */
export function groupKeyOf(p: Pick<SkuProduct, "brand" | "subcategory">): string {
  return `${p.brand ?? ""}|${p.subcategory ?? ""}`;
}

export function groupLabelOf(brand: string | null, subcategory: string | null): string {
  if (brand && subcategory) return `${brand} · ${subcategory}`;
  return brand || subcategory || "Other";
}

function compareVariants(sortBy: SortOption) {
  return (a: SkuProduct, b: SkuProduct): number => {
    const byName = a.name.localeCompare(b.name);
    switch (sortBy) {
      case "On-shelf stock (high → low)":
        return b.onShelfStock - a.onShelfStock || byName;
      case "On-shelf stock (low → high)":
        return a.onShelfStock - b.onShelfStock || byName;
      case "Confidence (high → low)":
        return b.confidence - a.confidence || byName;
      case "Name (A → Z)":
        return byName;
    }
  };
}

function compareGroups(sortBy: SortOption) {
  return (a: ProductGroup, b: ProductGroup): number => {
    const byLabel = a.label.localeCompare(b.label);
    switch (sortBy) {
      case "On-shelf stock (high → low)":
        return b.totalUnits - a.totalUnits || byLabel;
      case "On-shelf stock (low → high)":
        return a.totalUnits - b.totalUnits || byLabel;
      case "Confidence (high → low)":
        return (b.confidence ?? -1) - (a.confidence ?? -1) || byLabel;
      case "Name (A → Z)":
        return byLabel;
    }
  };
}

export function groupProducts(products: SkuProduct[], sortBy: SortOption): ProductGroup[] {
  const byKey = new Map<string, SkuProduct[]>();
  for (const p of products) {
    const key = groupKeyOf(p);
    const list = byKey.get(key);
    if (list) list.push(p);
    else byKey.set(key, [p]);
  }

  const groups: ProductGroup[] = [];
  for (const [key, list] of byKey) {
    const variants = [...list].sort(compareVariants(sortBy));
    const first = variants[0];
    const totalUnits = variants.reduce((sum, v) => sum + v.onShelfStock, 0);
    const weighted = variants.reduce((sum, v) => sum + v.confidence * v.onShelfStock, 0);
    const packs = new Set(variants.map((v) => `${v.packType} ${v.packSize}`));
    groups.push({
      key,
      label: groupLabelOf(first.brand, first.subcategory),
      primaryCategory: first.primaryCategory,
      thumbnail: first.thumbnail,
      variants,
      totalUnits,
      variantsOnShelf: variants.filter((v) => v.onShelfStock > 0).length,
      flaggedCount: variants.filter((v) => v.cvOutput.is_flagged).length,
      confidence: totalUnits > 0 ? weighted / totalUnits : null,
      packLabel: packs.size === 1 ? [...packs][0] : "Mixed",
      storesAvailable: Math.max(...variants.map((v) => v.storesAvailable)),
      storesTotal: Math.max(...variants.map((v) => v.storesTotal)),
    });
  }
  return groups.sort(compareGroups(sortBy));
}
