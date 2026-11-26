import assert from "node:assert/strict";
import { test } from "node:test";
import { parseImportFile } from "./import-parse.ts";

test("JSON: a list, or an object with items", () => {
  assert.deepEqual(parseImportFile("a.json", '[{"sku_id":"A"}]'), [{ sku_id: "A" }]);
  assert.deepEqual(parseImportFile("A.JSON", '{"items":[{"sku_id":"A"}]}'), [{ sku_id: "A" }]);
  assert.deepEqual(parseImportFile("a.json", '{"sku_id":"A"}'), []);
});

test("CSV: header row, BOM, quotes, CRLF, empty cells", () => {
  const text = '﻿"sku_id","brand","barcode"\r\n"A","TH",""\r\n\r\nB,Slide,893\r\n';
  assert.deepEqual(parseImportFile("skus.csv", text), [
    { sku_id: "A", brand: "TH" },
    { sku_id: "B", brand: "Slide", barcode: "893" },
  ]);
});

test("nothing to import", () => {
  assert.deepEqual(parseImportFile("skus.csv", ""), []);
  assert.deepEqual(parseImportFile("skus.csv", "sku_id,brand\n"), []);
});
