import assert from "node:assert/strict";
import { test } from "node:test";
import {
  frameLegend,
  namesText,
  notInViewNote,
  notInViewText,
  shelfNowRows,
  shelfNowSummary,
  splitByPlan,
  stockStatusLabel,
  updatedText,
} from "./shelf-now.ts";

const p = (
  sku_id: string,
  unit_count: number,
  stock_status: "OOS" | "LOW" | "IN_STOCK" | "NOT_IN_VIEW" | null,
  in_shelf_plan = true
) => ({
  sku_id,
  sku_name: sku_id,
  image_url: null,
  unit_count,
  in_shelf_plan,
  stock_status,
  ...(stock_status === "NOT_IN_VIEW"
    ? { not_in_view: { since: "2026-11-28T12:15:00+07:00", last_units: unit_count, last_at: "2026-11-28T12:10:00+07:00" } }
    : {}),
});

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
  assert.deepEqual(shelfNowSummary(rows), { products: 5, units: 12, out: 1, low: 2, notInView: 0 });
});

test("no plan, or an older backend without the fields, gives no rows", () => {
  assert.deepEqual(shelfNowRows([]), []);
  assert.deepEqual(shelfNowRows([{ sku_id: "A", sku_name: "A", image_url: null, unit_count: 4 }]), []);
  assert.deepEqual(shelfNowSummary([]), { products: 0, units: 0, out: 0, low: 0, notInView: 0 });
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

test("a product not in view comes after low stock and before in stock", () => {
  const rows = shelfNowRows([p("Cheese", 3, "IN_STOCK"), p("TH", 6, "NOT_IN_VIEW"), p("Hot", 2, "LOW"), p("Sour", 0, "OOS")]);
  assert.deepEqual(
    rows.map((r) => r.status),
    ["OOS", "LOW", "NOT_IN_VIEW", "IN_STOCK"]
  );
  assert.deepEqual(rows[2].notInView, { since: "2026-11-28T12:15:00+07:00", lastUnits: 6, lastAt: "2026-11-28T12:10:00+07:00" });
  assert.equal(rows[0].notInView, null);
});

test("the summary leaves products not in view out of the units and counts them", () => {
  const rows = shelfNowRows([p("Cheese", 5, "IN_STOCK"), p("TH", 6, "NOT_IN_VIEW")]);
  assert.deepEqual(shelfNowSummary(rows), { products: 2, units: 5, out: 0, low: 0, notInView: 1 });
});

test("a product not in view reads Not in view", () => {
  assert.equal(stockStatusLabel("NOT_IN_VIEW"), "Not in view");
});

test("not in view says since when and what was seen last", () => {
  const now = new Date("2026-11-28T06:20:00Z"); // 13:20 in UTC+7
  assert.equal(
    notInViewText({ since: "2026-11-28T12:15:00+07:00", lastUnits: 6, lastAt: "2026-11-28T12:10:00+07:00" }, now),
    "since 12:15 · last seen 6 at 12:10"
  );
  assert.equal(
    notInViewText({ since: "2026-11-28T12:15:00+07:00", lastUnits: 0, lastAt: "2026-11-28T12:10:00+07:00" }, now),
    "since 12:15 · was out of stock at 12:10"
  );
  assert.equal(
    notInViewText({ since: "2026-11-27T20:00:00+07:00", lastUnits: 3, lastAt: "2026-11-27T19:55:00+07:00" }, now),
    "since 20:00 on 27/11 · last seen 3 at 19:55 on 27/11"
  );
  assert.equal(notInViewText({ since: "2026-11-28T12:15:00+07:00", lastUnits: null, lastAt: null }, now), "since 12:15");
});

test("a card of a product not in view says since when and where its frame is from", () => {
  const now = new Date("2026-11-28T06:20:00Z"); // 13:20 on 28/11 in UTC+7
  const info = { since: "2026-11-28T12:15:00+07:00", lastAt: "2026-11-28T12:10:00+07:00" };
  assert.equal(
    notInViewNote(info, 8, now),
    "Not in view since 12:15. The frame and its 8 boxes are from 12:10, when it was last seen.",
  );
  assert.equal(
    notInViewNote(info, 1, now),
    "Not in view since 12:15. The frame and its 1 box are from 12:10, when it was last seen.",
  );
  assert.equal(
    notInViewNote({ since: "2026-11-27T20:00:00+07:00", lastAt: "2026-11-27T19:55:00+07:00" }, 3, now),
    "Not in view since 20:00 on 27/11. The frame and its 3 boxes are from 19:55 on 27/11, when it was last seen.",
  );
  assert.equal(notInViewNote({ since: info.since, lastAt: null }, 0, now), "Not in view since 12:15.");
  assert.equal(notInViewNote(info, 0, now), "Not in view since 12:15.");
});
