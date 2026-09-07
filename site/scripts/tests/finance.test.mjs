import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import Database from "better-sqlite3";
import { compile } from "./typescript.mjs";

const require = createRequire(import.meta.url);
const source = await readFile(new URL("../../src/lib/db.ts", import.meta.url), "utf8");
const sentinels = await readFile(new URL("../../src/lib/sentinels.ts", import.meta.url), "utf8");
const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

function queries(conn) {
  const constants = { exports: {} };
  vm.runInNewContext(compile(sentinels, { commonJS: true }), { exports: constants.exports });
  const module = { exports: {} };
  vm.runInNewContext(compile(source, { commonJS: true }), {
    exports: module.exports,
    process: { cwd: () => "/synthetic/site", env: {} },
    require: (name) => {
      if (name === "./sentinels") return constants.exports;
      if (name === "node:path") return require(name);
      assert.equal(name, "better-sqlite3");
      return function FixtureDatabase(_path, options) {
        assert.deepEqual({ ...options }, { readonly: true, fileMustExist: true });
        return conn;
      };
    },
  });
  return module.exports;
}

function fixture(t) {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  const people = conn.prepare("INSERT INTO people (id, name) VALUES (?, ?)");
  for (const id of ["member", "other", "unlinked", "outside", "no-terms"]) people.run(id, id);
  const term = conn.prepare("INSERT INTO person_terms (person_id, chamber, start, end) VALUES (?, 'lower', ?, ?)");
  term.run("member", "2025-01-01", "2025-06-30");
  term.run("member", "2025-06-01", null);
  term.run("other", "2025-01-01", null);
  term.run("outside", "2023-01-01", "2024-12-31");
  const insert = conn.prepare(`INSERT INTO contributions
    (person_id, committee_entity_id, date, amount, from_entity_id, from_name, from_type, occupation)
    VALUES (@person, 99, @date, @amount, @id, @name, @type, @occupation)`);
  const receipt = (data) => insert.run({
    person: "member", date: "2025-06-15", amount: 100, id: 10,
    name: "Shared name", type: "Registrant", occupation: null, ...data,
  });
  for (const data of [
    { id: 10, amount: 120, date: "2025-01-01" },
    { id: 10, amount: -20 },
    { id: 11, amount: 100 },
    { id: 12, amount: 80, name: "A alias" },
    { id: 12, amount: 40, name: "Z alias", date: "2025-06-30" },
    { id: 0, amount: 90 },
    { id: 13, amount: 70 },
    { id: 14, amount: 60 },
    { id: null, amount: 9000 },
    { id: 15, amount: 0 },
    { id: 16, amount: -10 },
    { id: 10, amount: 8000, date: "2024-12-31" },
    { id: 10, amount: 7000, person: "other" },
    { id: 20, amount: 150, type: "Individual", occupation: "ENGINEER" },
    { id: 20, amount: -25, type: "Individual", occupation: " Engineer " },
    { id: 21, amount: 125, type: "Individual", occupation: "engineer" },
    { id: 0, amount: 25, type: "Individual", name: null, occupation: "" },
    { id: 22, amount: 3, type: "Individual" },
    { id: 23, amount: 2, type: "Individual" },
    { id: 24, amount: 1, type: "Individual" },
    { id: null, amount: 500, type: "Individual" },
    { amount: 2000, person: "outside" },
    { amount: 2000, person: "no-terms" },
  ]) receipt(data);
  return queries(conn);
}

test("donor rankings preserve entity identities, source types, refunds, and the top-five limit", (t) => {
  const result = structuredClone(fixture(t).moneyFor("member"));
  assert.deepEqual(result.committees, [
    { entityId: 12, name: "Z alias", total: 120, n: 2 },
    { entityId: 11, name: "Shared name", total: 100, n: 1 },
    { entityId: 10, name: "Shared name", total: 100, n: 2 },
    { entityId: 0, name: "Shared name", total: 90, n: 1 },
    { entityId: 13, name: "Shared name", total: 70, n: 1 },
  ]);
  assert.deepEqual(result.individuals, [
    { entityId: 21, name: "Shared name", total: 125, n: 1 },
    { entityId: 20, name: "Shared name", total: 125, n: 2 },
    { entityId: 0, name: null, total: 25, n: 1 },
    { entityId: 22, name: "Shared name", total: 3, n: 1 },
    { entityId: 23, name: "Shared name", total: 2, n: 1 },
  ]);
  assert.equal(result.total, 10311);
  assert.equal(result.n, 19);
});

test("missing receipt coverage remains distinct from zero receipts during service", (t) => {
  const db = fixture(t);
  assert.equal(db.moneyFor("unlinked"), null);
  for (const person of ["outside", "no-terms"]) {
    const result = structuredClone(db.moneyFor(person));
    assert.equal(result.total, 0);
    assert.equal(result.n, 0);
    assert.deepEqual(result.committees, []);
    assert.deepEqual(result.individuals, []);
  }
});
