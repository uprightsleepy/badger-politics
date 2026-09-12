import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { legislatorProfile } from "../../src/lib/legislator.ts";
import { ballotStatus } from "../../src/lib/ballot.ts";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

/** One Assembly member who resigned in mid-2021 and returned for 2025. */
function fixture(t) {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  const insert = (sql, rows) => {
    const stmt = conn.prepare(sql);
    for (const row of rows) stmt.run(...row);
  };
  insert("INSERT INTO sessions (id, identifier) VALUES (?, ?)",
    [["2023", "2023"], ["2025", "2025"], ["2025s1", "2025s1"]]);
  insert("INSERT INTO people (id, name, party, current_role, chamber, district) VALUES (?, ?, ?, ?, 'lower', ?)", [
    ["m", "Member", "Democratic", "Representative", 1],
    ["d1", "Peer One", "Democratic", "Representative", 2],
    ["d2", "Peer Two", "Democratic", "Representative", 3],
    ["r1", "Other Party", "Republican", "Representative", 4],
  ]);
  insert("INSERT INTO person_terms (person_id, chamber, district, start, end, end_label, end_url) VALUES ('m', 'lower', 1, ?, ?, ?, ?)", [
    ["2021-01-04", "2021-06-30", "Resigned", "https://example.invalid/resigned"],
    ["2025-01-06", null, null, null],
  ]);
  insert("INSERT INTO bills (id, session_id, identifier, status, died_without_hearing, source) VALUES (?, ?, ?, ?, ?, 'openstates')", [
    ["b1", "2025", "AB 1", "enacted", 0],
    ["b2", "2025", "AB 2", "vetoed", 0],
    ["b3", "2025", "AB 3", "introduced", 1],
    ["b4", "2025", "AB 4", "in_committee", 0],
    ["b5", "2025", "SB 5", "in_committee", 0],
    ["b6", "2023", "AB 6", "enacted", 0],
    ["bs", "2025s1", "AB 1", "introduced", 0],
  ]);
  // the first primary sponsor on a bill is its lead author
  insert("INSERT INTO sponsorships (bill_id, person_id, name, classification, is_primary) VALUES (?, ?, ?, ?, ?)", [
    ["b1", "m", "Member", "primary", 1],
    ["b2", "m", "Member", "primary", 1],
    ["b3", "m", "Member", "primary", 1],
    ["b6", "m", "Member", "primary", 1],
    ["b4", "d1", "Peer One", "primary", 1],
    ["b4", "m", "Member", "primary", 0],
    ["b5", "d1", "Peer One", "primary", 1],
    ["b5", "m", "Member", "cosponsor", 0],
  ]);
  const events = [];
  // twenty 2025 roll calls on two days, every time with the party majority
  for (let i = 1; i <= 20; i++) {
    events.push([`e${i}`, "b1", i <= 10 ? "2025-02-04" : "2025-03-11",
      [["m", "yes"], ["d1", "yes"], ["d2", "yes"], ["r1", "no"]]]);
  }
  // one special-session roll call against the party: too small a sample
  events.push(["es", "bs", "2025-09-02", [["m", "no"], ["d1", "yes"], ["d2", "yes"]]]);
  // chamber voting days around the resignation: one missed while in office,
  // two that fall in the out-of-office years
  events.push(["e21", "b6", "2021-03-02", [["d1", "yes"], ["d2", "yes"]]]);
  events.push(["e22", "b6", "2022-03-02", [["d1", "yes"], ["d2", "yes"]]]);
  events.push(["e23", "b6", "2023-03-02", [["d1", "yes"], ["d2", "yes"]]]);
  for (const [id, bill, date, records] of events) {
    conn.prepare("INSERT INTO vote_events (id, bill_id, date, chamber) VALUES (?, ?, ?, 'lower')").run(id, bill, date);
    for (const [person, option] of records) {
      conn.prepare("INSERT INTO vote_records VALUES (?, ?, ?)").run(id, person, option);
    }
  }
  conn.prepare(`INSERT INTO elections (person_id, cycle_year, office, district, on_ballot, is_incumbent, opponents_json, source)
    VALUES ('m', 2026, 'Assembly', 1, NULL, 1, ?, 'wec')`).run(JSON.stringify([
    { name: "Challenger", party: "Republican", ballot_status: "Approve" },
    { name: "Denied", party: "Independent", ballot_status: "Deny" },
  ]));
  queries(conn);
  return conn.prepare("SELECT * FROM people WHERE id = 'm'").get();
}

test("the profile derives attendance, loyalty, authorship and ballot status from the record", (t) => {
  const p = legislatorProfile(fixture(t));
  assert.equal(p.sitting, true);
  assert.deepEqual(p.agreement.map((a) => a.session), ["2025s1", "2025"], "newest session first");
  assert.deepEqual(p.loyalty, { session: "2025", pct: 100, n: 20 }, "one special-session vote is not a sample");

  assert.deepEqual(p.authorship.tally.map((x) => [x.status, x.bills.length]),
    [["enacted", 2], ["vetoed", 1], ["introduced", 1]]);
  assert.deepEqual([p.authorship.enacted, p.authorship.vetoed, p.authorship.noHearing], [2, 1, 1]);
  assert.deepEqual(p.authorship.coauthored.map((s) => s.identifier), ["AB 4"], "same house, signed on");
  assert.deepEqual(p.authorship.cosponsored.map((s) => s.identifier), ["SB 5"], "the other house");
  assert.deepEqual(p.biennium.authorship.led.map((s) => s.identifier).sort(), ["AB 1", "AB 2", "AB 3"],
    "the 2023 bill is career, not this biennium");

  const { blocks, openYears, ...totals } = p.attendance;
  assert.deepEqual(totals, { total: 22, missed: 1, days: 4 }, "out-of-office days are never missed votes");
  assert.deepEqual(blocks, [
    { kind: "year", year: 2025 },
    { kind: "gap", from: 2022, to: 2023, label: "Resigned", url: "https://example.invalid/resigned" },
    { kind: "year", year: 2021 },
  ]);
  assert.deepEqual([...openYears], [2025, 2021]);
  assert.deepEqual(p.biennium.attendance, { total: 21, missed: 0 });

  assert.deepEqual(p.ballot, { kind: "pending", year: 2026 });
  assert.deepEqual(p.opponents.map((o) => o.name), ["Challenger"], "denied filings are not opponents");
});

test("ballot status reads the Commission's report and never infers a candidacy or a retirement", () => {
  assert.deepEqual(ballotStatus(null), { kind: "none" });
  assert.deepEqual(ballotStatus({ cycle_year: 2026, on_ballot: 1 }), { kind: "on-ballot", year: 2026 });
  assert.deepEqual(ballotStatus({ cycle_year: 2026, on_ballot: 0 }), { kind: "not-running", year: 2026 });
  assert.deepEqual(ballotStatus({ cycle_year: 2026, on_ballot: null }), { kind: "pending", year: 2026 });
  assert.deepEqual(ballotStatus({ cycle_year: 2028, on_ballot: null }), { kind: "future", year: 2028 });
});
