import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");
const gloss = await import("../../src/lib/localGloss.ts");
const vocabularies = [["old", "Aye", "No"], ["new", "Aye", "Nay"], ["civicclerk", "Yes", "No"]];

function fixture(t) {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  for (const [tenant, positive, negative] of vocabularies) {
    conn.prepare("INSERT INTO local_bodies VALUES (?, ?, ?, 'Council', 'https://example.invalid', 3)")
      .run(tenant, tenant, tenant);
    for (const id of [1, 2, 3, 9]) {
      conn.prepare("INSERT INTO local_members (tenant, person_id, name, slug) VALUES (?, ?, ?, ?)")
        .run(tenant, id, `Member ${id}`, `member-${id}`);
    }
    conn.prepare("INSERT INTO local_events VALUES (?, 1, '2026-01-01', 'Final', 'https://example.invalid/meeting')")
      .run(tenant);
    const casts = [
      [1, 1, [[1, negative], [2, positive], [3, positive]]],
      [2, 0, [[1, positive], [2, negative], [3, negative]]],
      [3, 1, [[1, "Abstained"], [2, positive], [3, positive]]],
      [4, 0, [[9, negative], [2, positive], [3, "No"]]],
      [5, null, [[1, negative]]],
    ];
    for (const [id, passed, votes] of casts) {
      conn.prepare("INSERT INTO local_actions (tenant, event_item_id, event_id, action, passed) VALUES (?, ?, 1, 'Adopted', ?)")
        .run(tenant, id, passed);
      for (const [person, value] of votes) {
        conn.prepare("INSERT INTO local_votes VALUES (?, ?, ?, ?)").run(tenant, id, person, value);
      }
    }
  }
  return { conn, api: queries(conn) };
}

test("council vocabularies yield identical totals without changing records or mixing cities", t => {
  const { api } = fixture(t);
  for (const [tenant, positive, negative] of vocabularies) {
    assert.deepEqual(api.localMemberVoteStats(tenant, 1), {
      total: 4, noes: 2, other: 1, last: "2026-01-01",
    });
    assert.deepEqual(api.localMemberOutcomes(tenant, 1), { lost: 2, decided: 2 });
    assert.deepEqual(api.localActionsWithDissent(tenant, 10).map(v => [v.event_item_id, v.ayes, v.noes]),
      [[4, 1, 2], [2, 1, 2], [1, 2, 1]]);
    assert.deepEqual(api.localMemberVotesWithDissent(tenant, 1).map(v => [v.event_item_id, v.value]),
      [[2, positive], [1, negative]]);
    assert.deepEqual(api.localMemberVotes(tenant, 1, 10).map(v => v.value),
      [negative, "Abstained", positive, negative]);
    const ties = api.localMemberTieBreaks(tenant, 9);
    assert.equal(ties.length, 1);
    assert.deepEqual([ties[0].value, ties[0].other_ayes, ties[0].other_noes], [negative, 1, 1]);
  }
});

test("negative vote labels share a display style without classifying other positions as no", () => {
  assert.equal(gloss.castStyle("Nay"), gloss.castStyle("No"));
  assert.equal(gloss.voteGloss("Nay"), "voted no");
  assert.equal(gloss.castStyle("Yes"), gloss.castStyle("Aye"));
  assert.equal(gloss.voteGloss("Yes"), "voted yes");
  for (const value of ["Yes", "Aye"]) assert.equal(gloss.isYesVote(value), true);
  for (const value of ["Nay", "No"]) assert.equal(gloss.isNoVote(value), true);
  for (const value of ["Aye", "Yes", "Abstained", "Presiding", "No Vote", "Unknown"]) {
    assert.equal(gloss.isNoVote(value), false);
  }
  for (const value of ["No", "Nay", "Present", "Unanimous"]) {
    assert.equal(gloss.isYesVote(value), false);
  }
});
