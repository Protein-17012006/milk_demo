// Unit tests for the product thumbnail (run: npm test).
import { test } from "node:test";
import assert from "node:assert/strict";
import { PLACEHOLDER_THUMBNAIL, productThumbnail } from "./product-thumbnail.ts";

test("a SKU shows the photo its SKU master row names", () => {
  assert.equal(
    productThumbnail("/images/products/slide-cheese-145g.png"),
    "/images/products/slide-cheese-145g.png"
  );
  assert.equal(
    productThumbnail("https://cdn.example.com/sku/8934680011709.png"),
    "https://cdn.example.com/sku/8934680011709.png"
  );
  assert.equal(
    productThumbnail("  /images/products/slide-hot-spicy-160g.png "),
    "/images/products/slide-hot-spicy-160g.png"
  );
});

test("a SKU without a photo shows the neutral box, not a photo guessed from its brand", () => {
  for (const missing of [null, undefined, "", "   "]) {
    assert.equal(productThumbnail(missing), PLACEHOLDER_THUMBNAIL);
  }
});

test("only site paths and https links are used as an image source", () => {
  for (const bad of [
    "javascript:alert(1)",
    "data:image/png;base64,AAAA",
    "http://example.com/a.png",
    "//example.com/a.png",
    "images/products/a.png",
  ]) {
    assert.equal(productThumbnail(bad), PLACEHOLDER_THUMBNAIL, bad);
  }
});
