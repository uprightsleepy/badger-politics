import assert from "node:assert/strict";
import test from "node:test";
import { attendanceTotals, buildHeatDays } from "../../src/lib/service.ts";

const term = (chamber, start, end = null) => ({
  chamber, start, end, district: 1, end_label: null, end_url: null,
});
const day = (date, n, chamber = "lower") => ({ date, n, chamber });
const cast = (date, count, nv = 0, chamber = "lower") => ({ date, cast: count, nv, chamber });

test("empty histories and days outside service contribute no totals", () => {
  assert.deepEqual(attendanceTotals([]), { total: 0, missed: 0 });
  assert.deepEqual(attendanceTotals(buildHeatDays([], [], [day("2025-01-01", 5)])), {
    total: 0, missed: 0,
  });
  assert.deepEqual(attendanceTotals([
    { date: "2024-01-01", total: 99, cast: 0, nv: 0, served: false },
  ]), { total: 0, missed: 0 });
});

test("resignation includes the final service day and excludes later voting days", () => {
  const heat = buildHeatDays(
    [term("lower", "2025-01-01", "2025-05-10")],
    [cast("2025-05-09", 2, 1), cast("2025-05-10", 0, 1)],
    [day("2024-12-31", 10), day("2025-05-09", 4), day("2025-05-10", 3), day("2025-05-11", 6)],
  );
  assert.deepEqual(heat.map((d) => d.date), ["2025-05-09", "2025-05-10"]);
  assert.deepEqual(attendanceTotals(heat), { total: 7, missed: 3 });
});

test("recall and comeback retain the heatmap gap without counting it as missed", () => {
  const heat = buildHeatDays(
    [term("lower", "2023-01-01", "2023-06-30"), term("lower", "2025-01-01")],
    [cast("2023-06-30", 3), cast("2024-02-01", 9), cast("2025-01-01", 2, 2)],
    [day("2023-06-30", 4), day("2024-02-01", 100), day("2025-01-01", 5)],
  );
  const gap = heat.find((d) => d.date === "2024-02-01");
  assert.deepEqual(gap, { date: "2024-02-01", total: 100, cast: 0, nv: 0, served: false });
  assert.deepEqual(attendanceTotals(heat), { total: 9, missed: 2 });
  assert.deepEqual(attendanceTotals(heat.filter((d) => d.date >= "2025-01-01")), {
    total: 5, missed: 1,
  });
});

test("overlapping service terms do not count a chamber's voting day twice", () => {
  const heat = buildHeatDays(
    [term("lower", "2025-01-01", "2025-06-30"), term("lower", "2025-03-01")],
    [cast("2025-03-15", 2, 1)],
    [day("2025-03-15", 5)],
  );
  assert.equal(heat.length, 1);
  assert.deepEqual(attendanceTotals(heat), { total: 5, missed: 2 });
});

test("a same-day chamber transfer does not create outgoing-chamber absences", () => {
  const heat = buildHeatDays(
    [term("upper", "2023-01-01", "2025-01-06"), term("lower", "2025-01-06")],
    [cast("2025-01-05", 3, 0, "upper"), cast("2025-01-06", 2, 1)],
    [day("2025-01-05", 4, "upper"), day("2025-01-06", 8, "upper"), day("2025-01-06", 3)],
  );
  assert.deepEqual(heat.filter((d) => d.date === "2025-01-06"), [
    { date: "2025-01-06", total: 3, cast: 2, nv: 1, served: true },
    { date: "2025-01-06", total: 8, cast: 0, nv: 0, served: false },
  ]);
  assert.deepEqual(attendanceTotals(heat), { total: 7, missed: 1 });
});

test("missing participation is missed while recorded nonvoting positions are not", () => {
  const heat = buildHeatDays(
    [term("lower", "2025-01-01")],
    [cast("2025-01-02", 1, 2), cast("2025-01-04", 0, 3)],
    [day("2025-01-02", 4), day("2025-01-03", 5), day("2025-01-04", 3)],
  );
  assert.deepEqual(heat.find((d) => d.date === "2025-01-03"), {
    date: "2025-01-03", total: 5, cast: 0, nv: 0, served: true,
  });
  assert.deepEqual(attendanceTotals(heat), { total: 12, missed: 6 });
});

test("excess participation on one day cannot cancel another day's missed votes", () => {
  const heat = Object.freeze([
    Object.freeze({ date: "2025-01-02", total: 2, cast: 4, nv: 0, served: true }),
    Object.freeze({ date: "2025-01-03", total: 5, cast: 2, nv: 1, served: true }),
  ]);
  assert.deepEqual(attendanceTotals(heat), { total: 7, missed: 2 });
  assert.equal(heat[0].cast, 4);
});

test("the API date window includes January 1 and does not narrow lifetime profile totals", () => {
  const heat = buildHeatDays(
    [term("lower", "2024-01-01")],
    [cast("2024-12-31", 2), cast("2025-01-01", 1, 1), cast("2025-01-02", 0, 2)],
    [day("2024-12-31", 3), day("2025-01-01", 4), day("2025-01-02", 2)],
  );
  assert.deepEqual(attendanceTotals(heat), { total: 9, missed: 3 });
  assert.deepEqual(attendanceTotals(heat.filter((d) => d.date >= "2025-01-01")), {
    total: 6, missed: 2,
  });
});
