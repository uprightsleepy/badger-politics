import assert from "node:assert/strict";
import test from "node:test";
import { heardSince, isNewSince, splitBillId } from "../../src/scripts/follows.ts";
import { wisconsinToday } from "../../src/lib/today.ts";

test("today is Wisconsin's date, not UTC's, on either side of midnight", () => {
  // 9:30 PM CDT is already the next day in UTC
  assert.equal(wisconsinToday(new Date("2026-10-12T02:30:00Z")), "2026-10-11");
  assert.equal(wisconsinToday(new Date("2026-10-12T05:30:00Z")), "2026-10-12");
  // CST in winter: 6 hours behind
  assert.equal(wisconsinToday(new Date("2026-01-02T05:59:00Z")), "2026-01-01");
});

test("an evening visit still sees the next day's action as new", () => {
  const seen = wisconsinToday(new Date("2026-10-12T02:30:00Z"));
  assert.equal(isNewSince(seen, "2026-10-12"), true);
  assert.equal(isNewSince(seen, "2026-10-11"), false, "the visit's own day was already seen");
  assert.equal(isNewSince(null, "2026-10-12"), false, "a first visit has nothing to compare");
  assert.equal(isNewSince(seen, null), false);
});

test("a committee is new for a hearing held since the visit, not one still ahead", () => {
  assert.equal(heardSince("2026-10-01", ["2026-09-30", "2026-10-20"], "2026-10-11"), false);
  assert.equal(heardSince("2026-10-01", ["2026-10-05"], "2026-10-11"), true);
  assert.equal(heardSince("2026-10-01", ["2026-10-11"], "2026-10-11"), false, "today's hearing may not have happened");
});

test("a bill id splits at its last hyphen, so special sessions keep theirs", () => {
  assert.deepEqual(splitBillId("2013s-dec-ab1"), { session: "2013s-dec", slug: "ab1" });
  assert.deepEqual(splitBillId("2025-ab656"), { session: "2025", slug: "ab656" });
});
