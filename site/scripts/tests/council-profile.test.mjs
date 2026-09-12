import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { councilMemberProfile } from "../../src/lib/council.ts";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

/** Three alderpersons and a presiding mayor over two meetings. */
function fixture(t) {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  const insert = (sql, rows) => {
    const stmt = conn.prepare(sql);
    for (const row of rows) stmt.run(...row);
  };
  conn.prepare("INSERT INTO local_bodies VALUES ('t', 't', 'Town', 'Common Council', 'https://example.invalid', 3)").run();
  insert("INSERT INTO local_members (tenant, person_id, name, slug, seat, is_current) VALUES ('t', ?, ?, ?, ?, 1)",
    [[1, "Ald One", "ald-one", 1], [2, "Ald Two", "ald-two", 2], [3, "Ald Three", "ald-three", 3], [9, "Mayor", "mayor", null]]);
  insert("INSERT INTO local_events VALUES ('t', ?, ?, 'Final', ?)",
    [[1, "2026-01-06", "https://example.invalid/m1"], [2, "2025-06-03", "https://example.invalid/m2"]]);
  insert("INSERT INTO local_actions (tenant, event_item_id, event_id, action, passed, mover_id) VALUES ('t', ?, ?, ?, ?, ?)", [
    [1, 1, "Adopted", 1, 1],
    [2, 2, "Referred", null, null],
    [3, 1, "Adopted", 1, null],
    [4, 2, "Adopted", 1, null],
  ]);
  insert("INSERT INTO local_votes VALUES ('t', ?, ?, ?)", [
    [1, 1, "No"], [1, 2, "Aye"], [1, 3, "Aye"],                    // the only No
    [2, 1, "Aye"], [2, 2, "No"], [2, 3, "Aye"],                    // no outcome recorded
    [3, 1, "Excused"], [3, 2, "Aye"], [3, 3, "No"], [3, 9, "Aye"], // the mayor breaks a tie
    [4, 1, "Aye"], [4, 2, "Aye"], [4, 3, "Aye"], [4, 9, "Aye"],    // unanimous, mayor included
  ]);
  insert("INSERT INTO local_member_terms VALUES ('t', ?, ?, ?, ?)",
    [[1, "Ald.", "2024-04-16", "2028-04-18"], [9, "Mayor", "2024-04-16", null]]);
  insert("INSERT INTO local_rollcalls VALUES ('t', ?, ?, 1, ?)",
    [[1, 1, "Present"], [3, 1, "Present"], [2, 2, "Excused"]]);
  conn.prepare("INSERT INTO local_memberships VALUES ('t', 1, 5, 'Finance Committee', 'Chair', NULL, NULL, 'https://example.invalid/finance')").run();
  queries(conn);
  return (id) => conn.prepare("SELECT * FROM local_members WHERE tenant = 't' AND person_id = ?").get(id);
}

test("an alderperson's record: stats, dissent, outcomes, attendance, term and glossary", (t) => {
  const p = councilMemberProfile("t", fixture(t)(1));
  assert.deepEqual(p.stats, { total: 4, noes: 1, other: 1, last: "2026-01-06" });
  assert.deepEqual(p.dissentVotes.map((v) => v.event_item_id), [3, 1, 2], "newest meeting first");
  assert.deepEqual(p.soleNoes.map((v) => v.event_item_id), [1]);
  assert.deepEqual(p.outcomes, { lost: 1, decided: 2 }, "an item with no outcome flag is not decided");
  assert.equal(p.motionCount, 1);
  assert.deepEqual(p.motions.map((m) => m.event_item_id), [1]);
  assert.deepEqual(p.attendance, {
    meetings: 2, present: 1, values: [{ value: "Present", n: 2 }, { value: "Excused", n: 1 }],
  });
  assert.deepEqual([p.termEnd, p.springYear, p.presiding, p.rated, p.tieBreaks],
    ["2028-04-18", "2028", false, true, []]);
  assert.deepEqual(p.committees.map((c) => c.body_name), ["Finance Committee"]);
  assert.deepEqual(p.yearPages, [{ year: "2026", page: 1 }, { year: "2025", page: 1 }]);
  assert.deepEqual(p.years, {
    soleNoes: [{ year: "2026", n: 1 }],
    dissent: [{ year: "2026", n: 2 }, { year: "2025", n: 1 }],
  });
  assert.deepEqual(p.glossary.map((g) => g.term).sort(),
    ["Adopted", "Aye", "Excused", "Present", "Referred"], "Yes/No are self-evident; the rest are glossed");
});

test("a presiding mayor is not rated; ties broken and Ayes that joined a unanimous council are counted", (t) => {
  const p = councilMemberProfile("t", fixture(t)(9));
  assert.deepEqual([p.presiding, p.rated, p.termEnd], [true, false, null]);
  assert.deepEqual(p.tieBreaks.map((v) => [v.event_item_id ?? 3, v.other_ayes, v.other_noes]), [[3, 1, 1]]);
  assert.equal(p.joinedAyes, 1);
  assert.deepEqual(p.soleNoes, []);
});
