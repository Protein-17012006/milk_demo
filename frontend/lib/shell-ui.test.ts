import assert from "node:assert/strict";
import { test } from "node:test";
import { AFTER_SIGN_IN, shellState } from "./shell-ui.ts";

test("what the page frame shows", () => {
  assert.equal(AFTER_SIGN_IN, "/dashboard");
  // never redirect while the session is still being read
  assert.equal(shellState({ isLoading: true, isAuthenticated: false, isApproved: false }), "loading");
  assert.equal(shellState({ isLoading: false, isAuthenticated: false, isApproved: false }), "to-login");
  // just registered: signed in, no group yet
  assert.equal(shellState({ isLoading: false, isAuthenticated: true, isApproved: false }), "waiting");
  assert.equal(shellState({ isLoading: false, isAuthenticated: true, isApproved: true }), "ready");
});
