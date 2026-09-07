import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { moduleUrl } from "./typescript.mjs";

const importer = await readFile(new URL("../../../pipeline/importer/import_federal.py", import.meta.url), "utf8");
const schema = importer.match(/conn\.executescript\(\s*"""([\s\S]*?)"""/)[1];
const paging = await import(moduleUrl(await readFile(new URL("../../src/lib/paging.ts", import.meta.url), "utf8")));

function fixture(t, count = 0) {
  const reads = [];
  const conn = new Database(":memory:", { verbose: sql => reads.push(sql) });
  t.after(() => conn.close());
  conn.exec(schema);
  const vote = conn.prepare(`INSERT INTO federal_votes VALUES
    (@id, @congress, @session, @chamber, @number, @date, @question, @result,
     @title, @yeas, @nays, @majority_requirement, @document, @source_url)`);
  const record = conn.prepare("INSERT INTO federal_vote_records VALUES (?, ?, 'Example', 'I', 'WI', ?)");
  const expected = Array.from({ length: count }, (_, i) => ({
    id: `s119-1-${i}`, congress: 119, session: 1, chamber: "senate", number: count - i,
    date: i < 250 ? "2025-06-02" : "2025-06-01", question: "Question & résumé?",
    result: i % 2 ? "Agreed to" : null, title: i % 3 ? "Title <with> quotes \"" : null,
    yeas: 51, nays: 49, majority_requirement: i % 2 ? "1/2" : null,
    document: i % 2 ? "S. 12" : null, source_url: `https://example.invalid/vote/${i}`,
    vote_cast: ["Yea", "Nay", "Not Voting", "Present", "Guilty", "Not Guilty"][i % 6],
  }));
  for (const row of [...expected].reverse()) {
    const { vote_cast, ...data } = row;
    vote.run(data);
    record.run(row.id, "S-example", vote_cast);
    // Chamber-native IDs remain distinct even for the same roll call.
    record.run(row.id, "B-example", "Present");
  }
  reads.length = 0;
  return { conn, api: queries(conn), expected, reads, record };
}

for (const count of [0, 1, 249, 250, 251, 500, 501]) {
  test(`complete federal history survives repeated reads and paging (${count} rows)`, t => {
    const { api, expected, reads } = fixture(t, count);
    const rows = api.federalVotesFor("S-example");
    assert.deepEqual(rows, expected);
    const size = paging.FEDERAL_VOTES_PER_PAGE;
    assert.equal(size, 250);
    const pages = Array.from({ length: paging.pageCount(rows.length, size) }, (_, i) =>
      api.federalVotesFor("S-example").slice(i * size, (i + 1) * size));
    assert.deepEqual(pages.flat(), expected);
    assert.deepEqual(api.federalVotesFor("S-example").slice(0, 5), expected.slice(0, 5));
    assert.deepEqual(api.federalVotesFor("S-example").slice(0, 25), expected.slice(0, 25));
    assert.deepEqual(api.federalVotesFor("B-example"), expected.map(row => ({ ...row, vote_cast: "Present" })));
    assert.deepEqual(api.federalVotesFor("unknown"), []);
    assert.deepEqual(api.federalVotesFor("unknown"), []);
    assert.equal(reads.filter(sql => sql.startsWith("SELECT v.*, r.vote_cast")).length, 3);
  });
}

test("tied votes and duplicate positions retain their original order and multiplicity", t => {
  const { conn, api, expected, record } = fixture(t, 251);
  // A tied sort key crosses the first page boundary; records were inserted in reverse order.
  conn.prepare("UPDATE federal_votes SET date = '2025-06-01', number = 1 WHERE id = ?").run(expected[249].id);
  record.run(expected[250].id, "S-example", "Nay");
  const ordered = [
    ...expected.slice(0, 249), expected[250],
    { ...expected[249], date: "2025-06-01", number: 1 },
    { ...expected[250], vote_cast: "Nay" },
  ];
  assert.deepEqual(api.federalVotesFor("S-example"), ordered);
  assert.deepEqual(api.federalVotesFor("S-example").slice(250), ordered.slice(250));
});

test("vote keys use only the source ID for the member's chamber", t => {
  const { api } = fixture(t);
  const member = { lis_id: "S-example", bioguide: "B-example" };
  assert.equal(api.federalVoteKey({ ...member, chamber: "senate" }), "S-example");
  assert.equal(api.federalVoteKey({ ...member, chamber: "house" }), "B-example");
  assert.equal(api.federalVoteKey({ ...member, chamber: "house", lis_id: null }), "B-example");
  // Missing Senate IDs must not silently fall back to another identifier.
  assert.equal(api.federalVoteKey({ ...member, chamber: "senate", lis_id: null }), null);
});

test("a new database module gets fresh results; a failed query can be retried", t => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  const oldSnapshot = queries(conn);
  assert.deepEqual(Array.from(oldSnapshot.federalMembers()), []);
  assert.equal(oldSnapshot.federalLatestVoteDate(), null);
  assert.throws(() => oldSnapshot.federalVotesFor("S-example"), /no such table: federal_votes/);
  conn.exec(schema);
  assert.deepEqual(oldSnapshot.federalVotesFor("S-example"), []);

  const { conn: next, expected } = fixture(t, 1);
  assert.deepEqual(queries(next).federalVotesFor("S-example"), expected);
});
