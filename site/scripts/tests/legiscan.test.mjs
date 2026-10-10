import assert from "node:assert/strict";
import test from "node:test";
import { isLegiscan, legiscanBillUrl, LEGISCAN_WI_URL } from "../../src/lib/legiscan.ts";

test("a regular-session bill links to its own LegiScan page", () => {
  assert.equal(legiscanBillUrl("2025", "AB 656"), "https://legiscan.com/WI/bill/AB656/2025");
  assert.equal(legiscanBillUrl("2023", "sjr 1"), "https://legiscan.com/WI/bill/SJR1/2023");
});

test("a special-session bill links to LegiScan's Wisconsin page rather than a guessed address", () => {
  assert.equal(legiscanBillUrl("2024s-jan", "AB 1"), LEGISCAN_WI_URL);
  assert.equal(legiscanBillUrl("2026s1", "SB 2"), LEGISCAN_WI_URL);
});

test("only rows marked legiscan are credited to LegiScan", () => {
  assert.equal(isLegiscan({ source: "legiscan" }), true);
  assert.equal(isLegiscan({ source: "openstates" }), false);
  assert.equal(isLegiscan({ source: null }), false);
  assert.equal(isLegiscan({}), false);
});
