import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

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

test("full-period receipts include pre-office history without changing the service view", (t) => {
  const db = fixture(t);
  const history = { start: "2007-01-01", end: "2026-12-31", inOffice: 0 };
  const full = db.moneyFor("member", history);
  assert.equal(full.total, 18311);
  assert.equal(full.n, 20);
  assert.equal(full.committees.find((c) => c.entityId === 10).total, 8100);
  assert.equal(full.quarters.reduce((total, q) => total + q.total, 0), full.total);
  assert.equal(full.byType.reduce((total, type) => total + type.total, 0), full.total);
  const service = db.moneyFor("member", { ...history, inOffice: 1 });
  assert.equal(service.total, 10311);
  assert.equal(service.n, 19, "overlapping terms must not duplicate receipts");
  for (const person of ["outside", "no-terms"]) {
    assert.equal(db.moneyFor(person, history).total, 2000);
    assert.equal(db.moneyFor(person, { ...history, inOffice: 1 }).total, 0);
  }
  assert.equal(db.moneyFor("unlinked", history), null);
});

test("overview, profiles, and donor recipients share period and service boundaries", (t) => {
  const db = fixture(t);
  const current = { start: "2025-01-01", end: "2026-12-31", inOffice: 0 };
  const overview = db.moneyOverview(current);
  assert.equal(overview.total, 21311);
  assert.equal(overview.total, ["member", "other", "outside", "no-terms"]
    .reduce((total, id) => total + db.moneyFor(id, current).total, 0));
  const donor = db.donorCommitteeFor(10, current);
  assert.equal(donor.summary.total, donor.recipients.reduce((total, r) => total + r.total, 0));
  assert.equal(donor.summary.total, donor.byParty.reduce((total, p) => total + p.total, 0));
  assert.equal(db.moneyOverview({ ...current, inOffice: 1 }).total, 17311);
  const earlier = db.moneyFor("member", { start: "2023-01-01", end: "2024-12-31", inOffice: 0 });
  assert.equal(earlier.total, 8000);
  assert.equal(earlier.n, 1, "the day immediately before the current period stays in the previous period");
  const empty = db.moneyFor("member", { start: "2027-01-01", end: "2028-12-31", inOffice: 0 });
  assert.equal(empty.n, 0);
  assert.equal(empty.total, 0);
  assert.deepEqual(structuredClone(empty.committees), []);
});

test("committee filings use the selected dates without a legislator service filter", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  conn.exec(`INSERT INTO cf_committees (entity_id,name,committee_type) VALUES
    (1,'Example PAC','PAC'), (2,'Candidate committee','State Candidate');
    INSERT INTO cf_transactions (id,filer_entity_id,direction,date,amount,other_name,stance,related_name) VALUES
    (1,1,'INCOMING','2024-12-31',100,'Earlier donor',NULL,NULL),
    (2,1,'INCOMING','2025-01-01',50,'Current donor',NULL,NULL),
    (3,1,'OUTGOING','2026-12-31',20,'Current payee','FOR','Example candidate'),
    (4,1,'OUTGOING','2027-01-01',30,'Later payee','AGAINST','Example candidate'),
    (5,2,'OUTGOING','2025-01-01',500,'Candidate advertising','FOR','Example candidate');`);
  const db = queries(conn);
  const bounds = { start: "2025-01-01", end: "2026-12-31", inOffice: 1 };
  const current = db.cfCommitteeFor(1, bounds);
  assert.equal(current.raised, 50);
  assert.equal(current.spent, 20);
  assert.equal(current.n, 2);
  assert.equal(current.donors[0].name, "Current donor");
  assert.equal(current.payees[0].name, "Current payee");
  assert.equal(current.advocacy.length, 1);
  assert.equal(current.advocacy[0].date, "2026-12-31");
  assert.equal(db.cfCommitteeFor(1).n, 4, "history remains available");
  assert.equal(db.cfCommitteeFor(2, bounds), null, "partial candidate advertising must not stand in for total campaign money");
});
