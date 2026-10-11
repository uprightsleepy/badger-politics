import assert from "node:assert/strict";
import { test } from "node:test";
import Database from "better-sqlite3";
import { queries as fixtureQueries } from "./database.mjs";

const BASE = `CREATE TABLE sessions (id TEXT, identifier TEXT, name TEXT, data_quality TEXT);
  INSERT INTO sessions VALUES ('2025','2025',NULL,NULL),('2011s-jan','2011s-jan',NULL,NULL);
  CREATE TABLE actions (bill_id TEXT, date TEXT, description TEXT);
  CREATE TABLE bills (id TEXT, session_id TEXT, identifier TEXT, title TEXT);
  INSERT INTO bills VALUES ('2025-ab1','2025','AB 1','A law'),('2011s-jan-ab11','2011s-jan','AB 11','Old law');`;

test("an older snapshot without the table shows no court challenges", () => {
  const db = new Database(":memory:");
  db.exec(BASE);
  const queries = fixtureQueries(db);
  assert.deepEqual(queries.courtChallengesFor("2025-ab1"), []);
  assert.deepEqual(queries.builtCourtChallenges(), []);
});

test("challenges attach to their own act, and the index lists only built bill pages", () => {
  const db = new Database(":memory:");
  db.exec(`${BASE}
    CREATE TABLE court_challenges (docket_id INTEGER, bill_id TEXT, court TEXT, case_name TEXT,
      docket_number TEXT, date_filed TEXT, date_terminated TEXT, date_last_filing TEXT, url TEXT,
      basis_url TEXT);
    INSERT INTO court_challenges VALUES
      (1,'2025-ab1','W.D. Wis.','Older v. State',NULL,'2025-01-01',NULL,NULL,'https://www.courtlistener.com/docket/1/a/','https://example.org'),
      (2,'2025-ab1','W.D. Wis.','Newer v. State',NULL,'2025-06-01',NULL,NULL,'https://www.courtlistener.com/docket/2/b/','https://example.org'),
      (3,'2011s-jan-ab11','E.D. Wis.','History v. State',NULL,'2011-03-01','2012-01-01',NULL,'https://www.courtlistener.com/docket/3/c/','https://example.org');`);
  const queries = fixtureQueries(db);
  const before = process.env.BUILD_SESSIONS;
  process.env.BUILD_SESSIONS = "2025";
  try {
    assert.deepEqual(queries.courtChallengesFor("2025-ab1").map((c) => c.docket_id), [2, 1]);
    assert.deepEqual(queries.builtCourtChallenges().map((c) => c.docket_id), [2, 1],
      "a challenge whose bill page is not built is left off the index");
  } finally {
    if (before === undefined) delete process.env.BUILD_SESSIONS;
    else process.env.BUILD_SESSIONS = before;
  }
});
