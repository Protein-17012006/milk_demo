// Unit tests for the Products grouping (run: npm test). Expected values are worked out by hand.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { SkuProduct } from "./products-ui";
import { groupKeyOf, groupLabelOf, groupProducts, groupSelection } from "./product-groups.ts";

type Over = Partial<SkuProduct> & { id: string };

/** A complete SkuProduct as the page builds it from GET /products, with test overrides. */
function sku(over: Over): SkuProduct {
  const base: SkuProduct = {
    id: over.id,
    name: over.id,
    modelAlias: over.id,
    thumbnail: "/images/products/placeholder.svg",
    categories: ["Milk"],
    primaryCategory: "Milk",
    packType: "Box",
    packSize: "180 ml",
    skuCode: over.id,
    barcode: "Pending SKU Master",
    brandManufacturer: "Vinamilk JSC",
    categoryPath: "Milk",
    onShelfStock: 0,
    confidence: 0,
    storesAvailable: 0,
    storesTotal: 1,
    storeRegion: "DEMO-S01",
    status: "Validated",
    brand: null,
    subcategory: null,
    cvOutput: {
      reading_id: "—", capture_id: "—", store_id: "DEMO-S01", camera_id: "CAM-S01-A",
      capture_timestamp: "—", capture_source: "CCTV", image_filename: "—", sku_id: over.id,
      sku_name: over.id, unit_count: 0, confidence_score: 0, detection_method: "Visual",
      bounding_box: [], is_flagged: false, flag_reason: "", processing_time_ms: 0, image_key: "",
      frame_w: 2560, frame_h: 1440, faces_blurred: 0, pipeline: "long",
    },
    audit: { accuracy: null, expectedLabel: over.id, mismatchType: "None", reviewedAt: null },
  };
  return { ...base, ...over };
}

/** A variant seen on the shelf and flagged (confidence below 0.70), as tonight's live rows are. */
function seen(over: Over, units: number, conf: number): SkuProduct {
  const p = sku({ ...over, onShelfStock: units, confidence: conf, storesAvailable: 1, status: "Low Confidence" });
  return { ...p, cvOutput: { ...p.cvOutput, unit_count: units, confidence_score: conf, is_flagged: true } };
}

const TH = { brand: "TH true MILK", subcategory: "Fresh Milk" };
const VNM_FRESH = { brand: "Vinamilk", subcategory: "Fresh Milk" };
const VNM_FLAV = { brand: "Vinamilk", subcategory: "Flavored Milk" };
const VNM_PLANT = { brand: "Vinamilk", subcategory: "Plant Milk" };
const SLIDE = { brand: "Slide", subcategory: "Potato Crisps", primaryCategory: "Snack" as const, packType: "Can" };

const slide4 = [
  seen({ id: "Slide Original 145g", ...SLIDE, packSize: "145 g" }, 1, 0.46),
  seen({ id: "Slide Cheese 145g", ...SLIDE, packSize: "145 g", thumbnail: "/t/cheese.png" }, 11, 0.44),
  seen({ id: "Slide Sour Cream & Onion 150g", ...SLIDE, packSize: "150 g" }, 1, 0.37),
  seen({ id: "Slide Hot & Spicy 160g", ...SLIDE, packSize: "160 g" }, 1, 0.3),
];

const catalog16 = [
  sku({ id: "TH 1", ...TH }), sku({ id: "TH 2", ...TH }),
  sku({ id: "VNM 1", ...VNM_FRESH }), sku({ id: "VNM 2", ...VNM_FRESH }), sku({ id: "VNM 3", ...VNM_FRESH }),
  sku({ id: "VNM 4", ...VNM_FLAV }), sku({ id: "VNM 5", ...VNM_FLAV }), sku({ id: "VNM 6", ...VNM_FLAV }),
  seen({ id: "VNM 7", ...VNM_PLANT }, 2, 0.5), sku({ id: "VNM 8", ...VNM_PLANT, confidence: 0.9 }),
  sku({ id: "VNM 9", ...VNM_PLANT }), sku({ id: "VNM 10", ...VNM_PLANT }),
  ...slide4,
];

test("16 catalog SKUs make 5 groups with brand · line labels and stable keys", () => {
  const groups = groupProducts(catalog16, "Name (A → Z)");
  assert.deepEqual(groups.map((g) => g.label), [
    "Slide · Potato Crisps", "TH true MILK · Fresh Milk", "Vinamilk · Flavored Milk",
    "Vinamilk · Fresh Milk", "Vinamilk · Plant Milk",
  ]);
  assert.deepEqual(groups.map((g) => g.key), [
    "Slide|Potato Crisps", "TH true MILK|Fresh Milk", "Vinamilk|Flavored Milk",
    "Vinamilk|Fresh Milk", "Vinamilk|Plant Milk",
  ]);
  assert.deepEqual(groups.map((g) => g.variants.length), [4, 2, 3, 3, 4]);
});

test("group totals: units, on-shelf variants, flagged, unit-weighted confidence", () => {
  const [g] = groupProducts(slide4, "On-shelf stock (high → low)");
  assert.equal(g.totalUnits, 14);
  assert.equal(g.variantsOnShelf, 4);
  assert.equal(g.flaggedCount, 4);
  // (11×0.44 + 0.46 + 0.37 + 0.30) / 14 = 5.97 / 14
  assert.ok(Math.abs((g.confidence ?? 0) - 5.97 / 14) < 1e-9);
  assert.deepEqual(g.variants.map((v) => v.name), [
    "Slide Cheese 145g", "Slide Hot & Spicy 160g", "Slide Original 145g", "Slide Sour Cream & Onion 150g",
  ]);
  assert.equal(g.thumbnail, "/t/cheese.png");
  assert.equal(g.primaryCategory, "Snack");
});

test("variants without units do not move the group confidence", () => {
  const plant = groupProducts(catalog16, "Name (A → Z)").find((g) => g.key === "Vinamilk|Plant Milk");
  assert.equal(plant?.confidence, 0.5); // VNM 8 has confidence 0.9 but 0 units
  assert.equal(plant?.variantsOnShelf, 1);
});

test("confidence is null when no variant has units", () => {
  const [g] = groupProducts([sku({ id: "a", ...VNM_FRESH }), sku({ id: "b", ...VNM_FRESH }), sku({ id: "c", ...VNM_FRESH })], "Name (A → Z)");
  assert.equal(g.confidence, null);
  assert.equal(g.totalUnits, 0);
  assert.equal(g.variantsOnShelf, 0);
  assert.equal(g.flaggedCount, 0);
});

test("labels fall back to brand, then line, then Other", () => {
  assert.equal(groupLabelOf("Vinamilk", "Plant Milk"), "Vinamilk · Plant Milk");
  assert.equal(groupLabelOf("Vinamilk", null), "Vinamilk");
  assert.equal(groupLabelOf(null, "Plant Milk"), "Plant Milk");
  assert.equal(groupLabelOf(null, null), "Other");
  assert.equal(groupKeyOf({ brand: "Vinamilk", subcategory: null }), "Vinamilk|");
  assert.equal(groupKeyOf({ brand: null, subcategory: null }), "|");
  const [other] = groupProducts([sku({ id: "x" }), sku({ id: "y" })], "Name (A → Z)");
  assert.equal(other.label, "Other");
  assert.equal(other.variants.length, 2);
});

test("pack label is the shared pack or Mixed", () => {
  const groups = groupProducts(catalog16, "Name (A → Z)");
  assert.equal(groups.find((g) => g.key === "Vinamilk|Fresh Milk")?.packLabel, "Box 180 ml");
  assert.equal(groups.find((g) => g.key === "Slide|Potato Crisps")?.packLabel, "Mixed");
});

test("stores: the most stores any variant is in, over the store total", () => {
  const [g] = groupProducts([
    sku({ id: "a", ...VNM_PLANT, storesAvailable: 1 }),
    sku({ id: "b", ...VNM_PLANT, storesAvailable: 1 }),
    sku({ id: "c", ...VNM_PLANT, storesAvailable: 0 }),
  ], "Name (A → Z)");
  assert.equal(g.storesAvailable, 1); // max, not the sum (2): one store holds both variants
  assert.equal(g.storesTotal, 1);
});

test("groups sort by total stock and by confidence, ties by label", () => {
  assert.deepEqual(groupProducts(catalog16, "On-shelf stock (high → low)").map((g) => g.label), [
    "Slide · Potato Crisps", "Vinamilk · Plant Milk", "TH true MILK · Fresh Milk",
    "Vinamilk · Flavored Milk", "Vinamilk · Fresh Milk",
  ]);
  assert.deepEqual(groupProducts(catalog16, "On-shelf stock (low → high)").map((g) => g.label), [
    "TH true MILK · Fresh Milk", "Vinamilk · Flavored Milk", "Vinamilk · Fresh Milk",
    "Vinamilk · Plant Milk", "Slide · Potato Crisps",
  ]);
  // Plant 0.5, Slide 5.97/14 ≈ 0.426, the rest have no confidence
  assert.deepEqual(groupProducts(catalog16, "Confidence (high → low)").map((g) => g.label), [
    "Vinamilk · Plant Milk", "Slide · Potato Crisps", "TH true MILK · Fresh Milk",
    "Vinamilk · Flavored Milk", "Vinamilk · Fresh Milk",
  ]);
});

test("group selection is all, some or none of its variants", () => {
  const [g] = groupProducts(slide4, "Name (A → Z)");
  const ids = slide4.map((p) => p.id);
  assert.equal(groupSelection(g, new Set(ids)), "all");
  assert.equal(groupSelection(g, new Set([ids[0]])), "some");
  assert.equal(groupSelection(g, new Set()), "none");
  assert.equal(groupSelection(g, new Set(["TH 1"])), "none");
});
