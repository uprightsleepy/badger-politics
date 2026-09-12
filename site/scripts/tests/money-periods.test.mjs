import assert from "node:assert/strict";
import test from "node:test";
import { currentMoneyCycle, moneyPeriods, moneyViews } from "../../src/lib/money-periods.ts";

test("current reporting period changes at the Central calendar boundary, independently of source freshness", () => {
  assert.equal(currentMoneyCycle(new Date("2027-01-01T05:59:59Z")), 2026);
  assert.equal(currentMoneyCycle(new Date("2027-01-01T06:00:00Z")), 2028);
  const periods = moneyPeriods(new Date("2026-09-10T12:00:00Z"));
  assert.equal(periods[0].key, "2026");
  assert.equal(periods[0].label, "2025–2026 · Current");
  assert.equal(periods.at(-1).label, "All available history");
  assert.ok(periods.some((p) => p.key === "2008"));
});

test("each available period has both scopes and exactly one full-period default", () => {
  const views = moneyViews(new Date("2026-09-10T12:00:00Z"));
  assert.equal(views.filter((v) => v.isDefault).length, 1);
  assert.equal(views.find((v) => v.isDefault).bounds.inOffice, 0);
  assert.equal(views.length, moneyPeriods(new Date("2026-09-10T12:00:00Z")).length * 2);
  for (const v of views) {
    assert.equal(v.bounds.inOffice, v.scope === "office" ? 1 : 0);
    assert.ok(v.bounds.start <= v.bounds.end);
  }
});
