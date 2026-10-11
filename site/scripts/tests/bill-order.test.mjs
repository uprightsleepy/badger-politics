import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

test("bills sort by prefix then number, and same-day actions by the order they were written", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  conn.exec("INSERT INTO sessions (id, identifier) VALUES ('2025', '2025')");
  const bill = conn.prepare("INSERT INTO bills (id, session_id, identifier) VALUES (?, '2025', ?)");
  for (const id of ["AB 100", "SB 2", "AB 10", "AB 2", "AJR 1", "AB 1"]) bill.run(`2025-${id}`, id);
  const action = conn.prepare("INSERT INTO actions (id, bill_id, date, description) VALUES (?, '2025-AB 1', '2025-01-02', ?)");
  for (let i = 0; i <= 10; i++) action.run(`2025-ab1-a${i}`, `step ${i}`);
  const db = queries(conn);
  assert.deepEqual(db.billsFor("2025").map((b) => b.identifier),
    ["AB 1", "AB 2", "AB 10", "AB 100", "AJR 1", "SB 2"]);
  assert.deepEqual(db.actionsFor("2025-AB 1").slice(-3).map((a) => a.description), ["step 8", "step 9", "step 10"]);
});
