import assert from "node:assert/strict";
import { test } from "node:test";
import {
  frameLegend,
  namesText,
  shelfNowRows,
  shelfNowSummary,
  splitByPlan,
  stockStatusLabel,
  updatedText,
} from "./shelf-now.ts";

const p = (
  sku_id: string,
  unit_count: number,
  stock_status: "OOS" | "LOW" | "IN_STOCK" | null,
  in_shelf_plan = true
) => ({ sku_id, sku_name: sku_id, image_url: null, unit_count, in_shelf_plan, stock_status });

test("the table lists the plan's products, the ones that need attention first", () => {
  const rows = shelfNowRows([
    p("Sour", 6, "IN_STOCK"),
    p("Hot", 2, "LOW"),
    p("Vinamilk", 0, null, false),
    p("TH", 0, "OOS"),
    p("Cheese", 3, "IN_STOCK"),
    p("Original", 1, "LOW"),
  ]);
  assert.deepEqual(
    rows.map((r) => [r.name, r.units, r.status]),
    [
      ["TH", 0, "OOS"],
      ["Original", 1, "LOW"],
      ["Hot", 2, "LOW"],
      ["Cheese", 3, "IN_STOCK"],
      ["Sour", 6, "IN_STOCK"],
    ]
  );
  assert.deepEqual(shelfNowSummary(rows), { products: 5, units: 12, out: 1, low: 2 });
});

test("no plan, or an older backend without the fields, gives no rows", () => {
  assert.deepEqual(shelfNowRows([]), []);
  assert.deepEqual(shelfNowRows([{ sku_id: "A", sku_name: "A", image_url: null, unit_count: 4 }]), []);
  assert.deepEqual(shelfNowSummary([]), { products: 0, units: 0, out: 0, low: 0 });
});

test("a row carries the product's photo and reliability badge", () => {
  const [row] = shelfNowRows([
    {
      ...p("Cheese", 3, "IN_STOCK"),
      image_url: "/images/products/slide-cheese-145g.png",
      reliability: { badge: "low" },
    },
  ]);
  assert.equal(row.imageUrl, "/images/products/slide-cheese-145g.png");
  assert.equal(row.badge, "low");
  assert.equal(shelfNowRows([p("Hot", 2, "LOW")])[0].badge, null);
});

test("labels and the update line", () => {
  assert.equal(stockStatusLabel("OOS"), "Out of stock");
  assert.equal(stockStatusLabel("LOW"), "Low");
  assert.equal(stockStatusLabel("IN_STOCK"), "In stock");
  const now = new Date("2026-11-26T13:40:00Z"); // 20:40 on 26/11 in UTC+7
  assert.equal(updatedText("2026-11-26T15:45:23+07:00", now), "Updated at 15:45");
  assert.equal(updatedText("2026-11-25T21:58:02+07:00", now), "Updated at 21:58 on 25/11");
  assert.equal(updatedText(null, now), null);
  assert.equal(namesText([]), "");
  assert.equal(namesText(["A"]), "A");
  assert.equal(namesText(["A", "B"]), "A and B");
  assert.equal(namesText(["A", "B", "C", "D"]), "A, B and 2 more");
});

test("products off the plan are set apart", () => {
  const items = [
    { id: 1, inShelfPlan: true },
    { id: 2, inShelfPlan: false },
    { id: 3, inShelfPlan: true },
  ];
  assert.deepEqual(splitByPlan(items), { onPlan: [items[0], items[2]], offPlan: [items[1]] });
});

test("the shelf photo's legend: one colour per product that has boxes", () => {
  const legend = frameLegend([
    {
      sku_name: "Cheese",
      boxes: [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
      ],
    },
    { sku_name: "Gone", boxes: [] },
    { sku_name: "Hot", boxes: [[9, 9, 9, 9]] },
  ]);
  assert.deepEqual(
    legend.map((l) => [l.name, l.count]),
    [
      ["Cheese", 2],
      ["Hot", 1],
    ]
  );
  assert.notEqual(legend[0].color, legend[1].color);
});
