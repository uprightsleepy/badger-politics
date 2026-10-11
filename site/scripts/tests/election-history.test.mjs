import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { mapsNote, questionSubject, resultSentence } from "../../src/lib/ballot.ts";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

test("each result before 2024 names the maps it was held under", () => {
  assert.equal(mapsNote(2024), null, "today's maps carry no note");
  assert.equal(mapsNote(2026), null);
  assert.equal(mapsNote(2022), "2022 maps");
  assert.equal(mapsNote(2020), "2011 maps");
  assert.equal(mapsNote(2014), "2011 maps");
});

test("referendum headings become subjects, and bare headings give none", () => {
  assert.equal(questionSubject("State of Wisconsin Election Officials Referendum - Question 2"), "Election officials");
  assert.equal(
    questionSubject("State of Wisconsin Delegation of Appropriation Power Referendum - QUESTION 1"),
    "Delegation of appropriation power",
  );
  assert.equal(questionSubject("State of Wisconsin Referendum"), null);
  assert.equal(questionSubject("STATE REFERENDUM"), null);
});

test("judicial races group by contest, Supreme Court first, newest year first", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  conn.exec(`INSERT INTO judicial_history VALUES
    (2023, 'spring', 'COURT OF APPEALS JUDGE', 4, 'Chris Taylor', 412491, 416853, 'https://elections.wi.gov/a.xlsx'),
    (2023, 'spring', 'JUSTICE OF THE SUPREME COURT', NULL, 'Daniel Kelly', 818391, 1843480, 'https://elections.wi.gov/a.xlsx'),
    (2023, 'spring', 'JUSTICE OF THE SUPREME COURT', NULL, 'Janet C. Protasiewicz', 1021822, 1843480, 'https://elections.wi.gov/a.xlsx'),
    (2025, 'spring', 'COURT OF APPEALS JUDGE', 2, 'Mark Gundrum', 461278, 468860, 'https://elections.wi.gov/b.xlsx');
    INSERT INTO referendum_history VALUES
      (2024, 'spring', 2, 'Q2', 685806, 483900, 1169706, 'u'),
      (2024, 'primary', 1, 'Q1', 521538, 704260, 1225798, 'u'),
      (2024, 'spring', 1, 'Q1', 638555, 534612, 1173167, 'u');`);
  const db = queries(conn);
  const races = db.judicialRaces();
  assert.deepEqual(races.map((r) => [r.year, r.district]), [[2025, 2], [2023, null], [2023, 4]]);
  const court = races[1];
  assert.deepEqual(court.candidates.map((c) => c.candidate), ["Janet C. Protasiewicz", "Daniel Kelly"]);
  assert.equal(resultSentence(court.candidates, court.total), "Janet C. Protasiewicz won with 55.4% of 1,843,480 votes cast.");
  assert.deepEqual(
    db.referendumResults().map((q) => [q.election, q.question]),
    [["primary", 1], ["spring", 1], ["spring", 2]],
    "the later election first within a year",
  );
});
