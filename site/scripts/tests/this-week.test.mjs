import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { addDays } from "../../src/lib/today.ts";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

test("a week's edges are calendar days, across months, years and clock changes", () => {
  assert.equal(addDays("2026-10-11", 6), "2026-10-17");
  assert.equal(addDays("2026-10-30", 6), "2026-11-05", "daylight saving ends Nov 1");
  assert.equal(addDays("2026-12-29", 6), "2027-01-04");
  assert.equal(addDays("2026-03-03", -6), "2026-02-25");
});

test("the week's actions: inclusive edges, built sessions only, newest first", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  conn.exec(`INSERT INTO sessions (id, identifier) VALUES ('2025', '2025'), ('2023', '2023');
    INSERT INTO bills (id, session_id, identifier, died_without_hearing, source) VALUES
      ('2025-ab1', '2025', 'AB 1', 0, 'openstates'), ('2023-ab1', '2023', 'AB 1', 0, 'openstates');
    INSERT INTO actions (id, bill_id, date, description) VALUES
      ('a1', '2025-ab1', '2026-10-04', 'Too early'),
      ('a2', '2025-ab1', '2026-10-05', 'First day'),
      ('a3', '2025-ab1', '2026-10-11', 'Today'),
      ('a4', '2023-ab1', '2026-10-08', 'Not a built session');`);
  const { actionsBetween } = queries(conn);
  const prior = process.env.BUILD_SESSIONS;
  process.env.BUILD_SESSIONS = "2025";
  t.after(() => (prior === undefined ? delete process.env.BUILD_SESSIONS : (process.env.BUILD_SESSIONS = prior)));
  assert.deepEqual(actionsBetween("2026-10-05", "2026-10-11").map((a) => a.description), ["Today", "First day"]);
});
