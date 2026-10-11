import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");
const ARCHIVE = "https://docs.legis.wisconsin.gov/code/executive_orders";

test("executive orders group by governor, then year, newest first; numbers repeat across governors", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  const add = conn.prepare(`INSERT INTO executive_orders (folder, governor, year, number, url)
    VALUES (?, ?, ?, ?, ?)`);
  for (const [folder, governor, year, number] of [
    ["2011_scott_walker", "Scott Walker", 2011, 1],
    ["2019_tony_evers", "Tony Evers", 2019, 1],
    ["2019_tony_evers", "Tony Evers", 2020, 72],
    ["2019_tony_evers", "Tony Evers", 2020, 73],
  ]) add.run(folder, governor, year, number, `${ARCHIVE}/${folder}/${year}_${number}.pdf`);
  const shape = queries(conn).executiveOrders().map((g) => [
    g.governor, g.years.map((y) => [y.year, y.orders.map((o) => o.number)])]);
  assert.deepEqual(shape, [
    ["Tony Evers", [[2020, [73, 72]], [2019, [1]]]],
    ["Scott Walker", [[2011, [1]]]],
  ]);
});
