# Products grouping and frame viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the Products list by brand + product line, and let the Validation Card open the face-blurred frame with the reading's boxes drawn on it.

**Architecture:** Pure functions in `frontend/lib/` compute the groups and the zoom region and are unit-tested with Node's built-in runner. React components render a group row above the existing SKU rows and a full-screen SVG viewer (frame as `<image>`, boxes as `<rect>`). No backend change: `GET /products` already returns `brand`/`subcategory`, and `GET /products/{sku}` already returns `frame_presigned_url` and `bounding_box`.

**Tech Stack:** Next.js 16.4.6 static export, React client components, Tailwind classes, lucide-react icons; `node --test --experimental-strip-types` (Node 22.16) for unit tests; puppeteer-core + installed Edge for the end-to-end check.

**Spec:** `docs/superpowers/specs/2026-11-22-products-grouping-frame-viewer-design.md`

## Global Constraints

- No new dependencies (runtime or dev). Unit tests run with `node --test --experimental-strip-types`.
- No backend or API change. Counts stay per SKU (`sku_id` = product name); CSV export unchanged.
- UI copy in English like the rest of the UI. Group label `"<brand> · <subcategory>"`, e.g. `Vinamilk · Plant Milk`; fallbacks `"<brand>"` then `"Other"`.
- No fake data: group values are sums/maxima of API values; `—` where there is none.
- Signed frame links are never logged, stored or printed.
- Modules under unit test import other project files with `import type` only (Node cannot resolve `@/`).
- `npm run build` passes. Lint adds no error beyond the 5 existing `react-hooks/set-state-in-effect`.
- Commits use `Nguyen Huy Hoang <193206418+Protein-17012006@users.noreply.github.com>` and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. The 15 s background refresh while a group is open or the viewer is open: the group must stay open and the viewer must stay open. Test in Task 4 step 2.
2. Escape in the viewer closes only the viewer, not the Validation Card under it. Test in Task 4 step 2.
3. A reading with no boxes or no frame link (a SKU at 0 units): "View frame" is disabled with its reason, and nothing crashes. Unit test in Task 3 step 1; end-to-end in Task 4 step 2.
4. Expired link (S3 answers 403): the viewer refetches the detail once, shows the notice and loads the image, with no retry loop. Test in Task 4 step 2 (puppeteer answers 403 to the first S3 request).
5. Search plus group selection: a search auto-expands matching groups, and the group checkbox selects only the variants still visible. Unit test in Task 1 step 1; end-to-end in Task 4 step 2.

---

### Task 1: Grouping logic

**Files:**
- Create: `frontend/lib/product-groups.ts`
- Test: `frontend/lib/product-groups.test.ts`
- Modify: `frontend/lib/products-ui.ts` (add `brand`, `subcategory` to `SkuProduct`)
- Modify: `frontend/components/category/CategoryProductsView.tsx` (`mapApiProductToSkuProduct` sets them from `ApiProduct.brand` / `.subcategory`)
- Modify: `frontend/package.json` (script `"test": "node --test --experimental-strip-types lib/*.test.ts"`)
- Modify: `frontend/tsconfig.json` (`"exclude": ["node_modules", "**/*.test.ts"]`, since the tests import `./x.ts`)

**Interfaces:**
- Produces, in `lib/product-groups.ts`:
  - `interface ProductGroup { key: string; label: string; primaryCategory: PrimaryCategory; thumbnail: string; variants: SkuProduct[]; totalUnits: number; variantsOnShelf: number; flaggedCount: number; confidence: number | null; packLabel: string; storesAvailable: number; storesTotal: number }`
  - `groupKeyOf(p: Pick<SkuProduct, "brand" | "subcategory">): string`, e.g. `"Vinamilk|Plant Milk"`, `"Vinamilk|"`, `"|"`.
  - `groupLabelOf(brand: string | null, subcategory: string | null): string`
  - `groupProducts(products: SkuProduct[], sortBy: SortOption): ProductGroup[]`: groups and variants sorted by `sortBy`. Group sort value: stock = `totalUnits`; confidence = `confidence ?? -1`; name = `label`. Ties break by label/name ascending.
  - `groupSelection(group: ProductGroup, selected: Set<string>): "all" | "some" | "none"`
- `SkuProduct` gains `brand: string | null; subcategory: string | null`.

- [ ] **Step 1: Write the failing tests** in `lib/product-groups.test.ts`, with a `sku(overrides)` factory building a full `SkuProduct`:

```ts
test("16 catalog SKUs make 5 groups with brand · line labels", () => {
  const labels = groupProducts(catalog16, "Name (A → Z)").map((g) => g.label);
  assert.deepEqual(labels, ["Slide · Potato Crisps", "TH true MILK · Fresh Milk",
    "Vinamilk · Flavored Milk", "Vinamilk · Fresh Milk", "Vinamilk · Plant Milk"]);
});
test("group totals: units, on-shelf variants, flagged, unit-weighted confidence", () => {
  // Slide: (11, 0.44, flagged) (1, 0.46, flagged) (1, 0.30, flagged) (1, 0.37, flagged)
  const g = groupProducts(slide4, "On-shelf stock (high → low)")[0];
  assert.equal(g.totalUnits, 14); assert.equal(g.variantsOnShelf, 4); assert.equal(g.flaggedCount, 4);
  assert.ok(Math.abs((g.confidence ?? 0) - 5.97 / 14) < 1e-9);
  assert.deepEqual(g.variants.map((v) => v.onShelfStock), [11, 1, 1, 1]);
});
test("confidence is null when no variant has units", () => { /* 3 variants at 0 units → g.confidence === null */ });
test("labels fall back to brand, then Other", () => {
  assert.equal(groupLabelOf("Vinamilk", null), "Vinamilk"); assert.equal(groupLabelOf(null, null), "Other");
});
test("pack label is shared pack or Mixed", () => { /* all Box/180 ml → "Box 180 ml"; Slide 145/150/160 g → "Mixed" */ });
test("stores: max available over variants", () => { /* storesAvailable [0,1,0] → 1; storesTotal 1 */ });
test("groups sort by total stock high → low", () => { /* Slide (14) before Vinamilk · Plant Milk (2) */ });
test("group selection is all, some or none of its variants", () => { /* {all ids} → "all"; {one} → "some"; {} → "none" */ });
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd frontend && npm test`
Expected: FAIL, `Cannot find module ... product-groups.ts`.

- [ ] **Step 3: Implement `lib/product-groups.ts`** with the interfaces above (type-only imports from `./products-ui`). Add the two `SkuProduct` fields, set them in the mapper, then add the npm script and the tsconfig exclude.

- [ ] **Step 4: Run tests and build**

Run: `npm test && npm run build`
Expected: `# fail 0`; build prints `✓ Compiled successfully` and the 7 routes.

- [ ] **Step 5: Commit**: `git add frontend/lib/product-groups.ts frontend/lib/product-groups.test.ts frontend/lib/products-ui.ts frontend/components/category/CategoryProductsView.tsx frontend/package.json frontend/tsconfig.json`, message `Products: group SKUs by brand and product line (logic + tests)`.

### Task 2: Group rows on the Products page

**Files:**
- Create: `frontend/components/category/ProductRow.tsx` (the existing SKU row moved out unchanged, plus `nested`)
- Create: `frontend/components/category/ProductGroupRow.tsx`
- Modify: `frontend/components/category/CategoryProductsView.tsx` (table body; PRODUCT header cell)

**Interfaces:**
- Consumes: `groupProducts`, `groupSelection`, `ProductGroup` (Task 1).
- Produces:
  - `ProductRow(props: { item: SkuProduct; selected: boolean; nested?: boolean; menuOpen: boolean; menuRef: React.RefObject<HTMLDivElement | null>; onToggleSelect(): void; onOpenDetails(): void; onToggleMenu(): void; onCopyCode(): void; onExportRow(): void })`
  - `ProductGroupRow(props: { group: ProductGroup; expanded: boolean; selection: "all" | "some" | "none"; onToggleExpand(): void; onToggleSelect(): void })`

- [ ] **Step 1: Move the SKU row** (the JSX inside `filteredProducts.map`) into `ProductRow` with the props above. Nothing else changes yet. `npm run build` passes, and the page still renders one row per SKU.
- [ ] **Step 2: Build `ProductGroupRow`.** It uses the same column widths as the header (32 / flex-[2.4] / 126 / 82 / 152 / 140 / 140 / 128 / 90 px).
  - Product cell: `ChevronRight` (rotated when open), the first variant's thumbnail, `label`, and `"{n} variants · {m} on shelf"`.
  - Category: pill with `primaryCategory`. Pack: `packLabel`. SKU code: `"{n} SKUs"`. Stock: `totalUnits units`.
  - Confidence: `confidence` as % with the same colour bar, plus `"{k} flagged"`; `—` when null.
  - Stores: `storesAvailable/storesTotal stores`. Actions: none.
  - Checkbox: tri-state; "some" shows lucide `Minus`.
  - The whole row toggles expansion, except the checkbox.
- [ ] **Step 3: Wire it in `CategoryProductsView`.**
  - `groups = useMemo(() => groupProducts(filteredProducts, sortBy), …)`.
  - `const [expandedKeys, setExpandedKeys] = useState<Set<string>>(() => new Set())`, so groups start collapsed.
  - `isExpanded = (k) => searchText !== "" || expandedKeys.has(k)`, with `searchText = (localSearch || sidebarSearch).trim()`.
  - Render each group row, then its variants as `<ProductRow nested …>` when expanded.
  - The group checkbox adds the group's variant ids when the selection is not "all", and removes them when it is.
  - In the PRODUCT header add a text button "Expand all" / "Collapse all". It flips between every group key and an empty set; its label follows `expandedKeys.size === groups.length`.
  - Do not touch `expandedKeys` in `loadLiveData`.
- [ ] **Step 4: Verify**: `npm run build`; `npx eslint components/category` shows only the existing error at the `loadLiveData` effect.
- [ ] **Step 5: Commit** `Products: one row per product line, variants on expand`.

### Task 3: Frame viewer in the Validation Card

**Files:**
- Create: `frontend/lib/frame-geometry.ts`, Test: `frontend/lib/frame-geometry.test.ts`
- Create: `frontend/components/category/FrameViewer.tsx`
- Modify: `frontend/lib/products-ui.ts`: `CvOutputRow.frame_url: string | null`; `SkuProduct.detailFetchedAt: number | null`
- Modify: `frontend/components/category/ProductDetailsModal.tsx`: button and viewer state
- Modify: `frontend/components/category/CategoryProductsView.tsx`: mapper sets `frame_url: null` and `detailFetchedAt: null`; split detail loading

**Interfaces:**
- Produces, in `lib/frame-geometry.ts`:
  - `type Box = [number, number, number, number]` (`[x, y, width, height]` in frame pixels)
  - `interface Region { x: number; y: number; w: number; h: number }`
  - `focusRegion(boxes: Box[], frameW: number, frameH: number): Region`:
    1. Take the union of the boxes, grown on every side by `max(w, h)` over the boxes.
    2. Widen to at least `frameW / 6`.
    3. Grow the short side to the frame's aspect ratio, keeping the centre.
    4. Shift and then clamp inside the frame.
    5. With no boxes, return the full frame.
- Produces, in `FrameViewer.tsx`: `FrameViewer(props: { url: string; boxes: Box[]; readingId: string; captureTimestamp: string; unitCount: number; confidence: number; facesBlurred: number; notice: string | null; onImageError(): void; onClose(): void })`
- Produces, in `CategoryProductsView`: `loadProductDetail(item: SkuProduct): Promise<void>`. It fetches `GET /products/{id}` and merges the result into `viewingProduct`, setting `frame_url = detail.cv_output.frame_presigned_url` and `detailFetchedAt = Date.now()` on top of the fields merged today. `handleOpenProductDetails` = `setViewingProduct(item)` + `loadProductDetail(item)`. The modal gets the new prop `onRefreshDetail(): Promise<void>`.

- [ ] **Step 1: Write the failing tests** in `lib/frame-geometry.test.ts`:

```ts
const near = (a: number, b: number) => Math.abs(a - b) < 0.01;
test("one small box: min width 1/6 frame, 16:9, centred on the box", () => {
  const r = focusRegion([[958, 277, 48, 12]], 2560, 1440);
  assert.ok(near(r.w, 2560 / 6) && near(r.h, 1440 / 6));
  assert.ok(near(r.x + r.w / 2, 982) && near(r.y + r.h / 2, 283));
});
test("box at the top edge stays inside the frame", () => {
  const r = focusRegion([[464, 1, 57, 40]], 2560, 1440);
  assert.ok(r.y >= 0 && r.y + r.h <= 1440 && r.x >= 0 && r.x + r.w <= 2560);
});
test("no boxes gives the full frame", () => {
  assert.deepEqual(focusRegion([], 2560, 1440), { x: 0, y: 0, w: 2560, h: 1440 });
});
test("boxes spread over the frame give the full frame", () => {
  assert.deepEqual(focusRegion([[0, 0, 100, 100], [2400, 1300, 150, 130]], 2560, 1440), { x: 0, y: 0, w: 2560, h: 1440 });
});
```

- [ ] **Step 2: Run them to see them fail.** `npm test` gives FAIL, cannot find `frame-geometry.ts`.
- [ ] **Step 3: Implement `focusRegion`.** Run `npm test` and expect `# fail 0`.
- [ ] **Step 4: Build `FrameViewer`.**
  - Layout: a fixed overlay at `z-[60]`, above the card's `z-50`.
  - Header: reading id · time · `{units} units` · confidence · `Faces blurred: {n}` · a toggle "Zoom to boxes" / "Full frame" · close button.
  - Frame size: read `naturalWidth`/`naturalHeight` with `new Image()`, which also fires `onerror` → `onImageError`.
  - Drawing: an `<svg viewBox>` set to `focusRegion(…)` or the full frame. It holds `<image href={url} width={W} height={H}/>` and one `<rect data-box fill="none" stroke="#FF4000" vectorEffect="non-scaling-stroke" strokeWidth={2}>` plus a number label per box.
  - Escape: a `window` keydown listener with `{ capture: true }` that calls `stopPropagation()` and `onClose()`, so the card's `document` listener never sees that Escape.
  - Show `notice` as a banner when it is not null.
- [ ] **Step 5: Wire up the modal.**
  - In "Capture & S3 Traceability", add a button "View frame". It is disabled when `!cvOutput.frame_url || cvOutput.bounding_box.length === 0`, with the reason `No frame stored for this reading`.
  - On click, if `Date.now() - detailFetchedAt > 600_000`, await `onRefreshDetail()` first.
  - Image error: allow one retry per opening. Await `onRefreshDetail()` and set the notice to `"The signed link expired, so the card reloaded the latest reading."`, adding `" It is now RD-…"` when the reading id changed.
  - A second error shows `"Frame could not be loaded."` with no further retry.
- [ ] **Step 6: Verify.** `npm test && npm run build` pass, and lint shows no new errors.
- [ ] **Step 7: Commit** `Validation Card: view the frame with the reading's boxes`.

### Task 4: End-to-end check, deploy, record

**Files:**
- Modify: scratchpad `browser/view_site.cjs` (new steps; not in the repo)
- Modify: Confluence HOANG-P10 Nhật ký; memory `frontend-deploy`

- [ ] **Step 1: Serve the build locally.** `./venv/Scripts/python.exe -m http.server 3000 --directory <frontend>/out` (the API's CORS already allows `http://localhost:3000`).
- [ ] **Step 2: Extend and run the Edge check** with `SITE=http://localhost:3000`. It must assert each item below and screenshot each state:
  - The list shows 5 group rows, all collapsed.
  - "Expand all" opens them all. After 20 s (one background refresh) they are still open.
  - Searching "Cheese" leaves the Slide group open with only the Cheese row.
  - Ticking the group checkbox selects only that visible row.
  - On a variant with units > 0, "View frame" shows an SVG whose `rect[data-box]` count equals the card's "Bounding Boxes (N)". After 20 s it is still open. "Full frame" changes the `viewBox`. Escape closes the viewer while the card stays open.
  - With request interception answering 403 to the first S3 image request, the expired-link notice appears and the image then loads.
  - A variant with 0 units shows "View frame" disabled.
- [ ] **Step 3: Deploy to Amplify** (zip `out/`, create-deployment, upload, start-deployment, poll until SUCCEED). Re-run step 2 against the Amplify site with `QUICK=1`.
- [ ] **Step 4: Push and record.** Push to `main`. Add a P10 Nhật ký entry with the commit ids, the Amplify job and the evidence, without links or secrets. Update memory `frontend-deploy` with the new check steps.
