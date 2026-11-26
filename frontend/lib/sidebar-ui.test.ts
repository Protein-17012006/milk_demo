import assert from "node:assert/strict";
import { test } from "node:test";
import { isCollapsed, isNavActive } from "./sidebar-ui.ts";

test("a narrow screen starts collapsed, and the user's own choice wins", () => {
  assert.equal(isCollapsed(null, true), true);
  assert.equal(isCollapsed(null, false), false);
  assert.equal(isCollapsed(false, true), false); // opened by hand on a phone
  assert.equal(isCollapsed(false, false), false); // then turned to landscape: still open
  assert.equal(isCollapsed(true, false), true); // collapsed by hand on a desktop
});

test("the current page", () => {
  assert.equal(isNavActive("/dashboard", "/"), true);
  assert.equal(isNavActive("/dashboard", "/dashboard/"), true);
  assert.equal(isNavActive("/category", "/"), false);
  assert.equal(isNavActive("/settings", "/settings/"), true);
  assert.equal(isNavActive("/model", "/model"), true);
  assert.equal(isNavActive("/model", "/models/"), false);
});
