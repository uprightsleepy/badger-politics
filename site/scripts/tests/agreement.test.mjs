import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { compareVotes } from "../../src/lib/agreement.ts";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

test("only roll calls where both voted Aye or No are counted", () => {
  assert.deepEqual(compareVotes("yynn.y", "ynyn.n"), { shared: 5, same: 2, differed: [1, 2, 5] });
  assert.deepEqual(compareVotes("...", "yny"), { shared: 0, same: 0, differed: [] });
});

function fixture(t) {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  const insert = (sql, rows) => {
    const stmt = conn.prepare(sql);
    for (const row of rows) stmt.run(...row);
  };
  insert("INSERT INTO sessions (id, identifier) VALUES (?, ?)", [["2025", "2025"], ["2023", "2023"]]);
  insert("INSERT INTO people (id, name, party, current_role, chamber, district) VALUES (?, ?, ?, ?, ?, ?)", [
    ["a", "Alpha", "Democratic", "Representative", "lower", 1],
    ["b", "Bravo", "Republican", "Representative", "lower", 2],
    ["gone", "Former", "Republican", null, "lower", 3],
    ["s", "Senator", "Republican", "Senator", "upper", 1],
  ]);
  insert("INSERT INTO bills (id, session_id, identifier, died_without_hearing, source) VALUES (?, ?, ?, 0, ?)", [
    ["b1", "2025", "AB 1", "openstates"],
    ["bl", "2025", "AB 2", "legiscan"],
    ["old", "2023", "AB 3", "openstates"],
  ]);
  const events = [
    ["e1", "b1", "2025-02-01", "lower", "openstates", [["a", "yes"], ["b", "yes"], ["gone", "no"]]],
    ["e2", "b1", "2025-02-02", "lower", "openstates", [["a", "yes"], ["b", "no"]]],
    ["e3", "b1", "2025-02-03", "lower", "openstates", [["a", "not voting"], ["b", "no"]]],
    // LegiScan's roll calls, by event or by bill, never reach the data file
    ["el", "b1", "2025-02-04", "lower", "legiscan", [["a", "yes"], ["b", "yes"]]],
    ["eb", "bl", "2025-02-05", "lower", "openstates", [["a", "yes"], ["b", "yes"]]],
    // only the former member voted: nothing to compare, so it's dropped
    ["eg", "b1", "2025-02-06", "lower", "openstates", [["gone", "yes"]]],
    ["es", "b1", "2025-03-01", "upper", "openstates", [["s", "no"]]],
    ["eo", "old", "2023-03-01", "lower", "openstates", [["a", "no"], ["b", "no"]]],
  ];
  for (const [id, bill, date, chamber, source, records] of events) {
    conn.prepare("INSERT INTO vote_events (id, bill_id, date, chamber, motion, source) VALUES (?, ?, ?, ?, 'Passage', ?)")
      .run(id, bill, date, chamber, source);
    for (const [person, option] of records) {
      conn.prepare("INSERT INTO vote_records VALUES (?, ?, ?)").run(id, person, option);
    }
  }
  return queries(conn);
}

test("a session's matrix: official roll calls, sitting members, one column each", (t) => {
  const { voteMatrix } = fixture(t);
  const { lower, upper } = voteMatrix("2025");
  assert.deepEqual(lower.rollCalls.map((e) => e.id), ["e1", "e2", "e3"]);
  assert.deepEqual(lower.members.map((m) => m.id), ["a", "b"]);
  assert.deepEqual(lower.votes, ["yy.", "ynn"]);
  assert.deepEqual(compareVotes(...lower.votes), { shared: 2, same: 1, differed: [1] });
  assert.deepEqual(upper.votes, ["n"]);
  assert.deepEqual(Object.keys(voteMatrix("2023")), ["lower"]);
});
