import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import Database from "better-sqlite3";
import { queries } from "./database.mjs";
import { billCard, personCard, shareCards } from "../../src/lib/share.ts";

const schema = await readFile(new URL("../../../pipeline/importer/schema.sql", import.meta.url), "utf8");

test("share cards cover the newest two bienniums, sitting members and 2026 races", (t) => {
  const conn = new Database(":memory:");
  t.after(() => conn.close());
  conn.exec(schema);
  conn.exec(`
    INSERT INTO sessions (id, identifier, name) VALUES
      ('2021', '2021', '2021 Regular Session'), ('2023', '2023', '2023 Regular Session'),
      ('2025', '2025', '2025 Regular Session'), ('2026s1', '2026s1', 'January 2026 Special Session');
    INSERT INTO bills (id, session_id, identifier, title, status, source) VALUES
      ('old', '2021', 'AB 1', 'Relating to: roads.', 'enacted', 'openstates'),
      ('prev', '2023', 'AB 2', 'Relating to: parks.', 'vetoed', 'openstates'),
      ('cur', '2025', 'SB 3', 'Relating to: schools.', 'in_committee', 'openstates'),
      ('ls', '2025', 'AB 4', 'Relating to: lakes.', 'introduced', 'legiscan'),
      ('sp', '2026s1', 'AB 1', NULL, 'introduced', 'openstates');
    INSERT INTO people (id, name, party, current_role, chamber, district) VALUES
      ('rep', 'Pat Doe', 'Democratic', 'Representative', 'lower', 12),
      ('sen', 'Lee Roe', 'Republican', 'Senator', 'upper', 7),
      ('gone', 'Former Member', 'Republican', NULL, 'lower', 3);
    INSERT INTO elections (person_id, cycle_year, district) VALUES ('rep', 2026, 12);
  `);
  const db = queries(conn);
  process.env.BUILD_SESSIONS = "all";
  t.after(() => delete process.env.BUILD_SESSIONS);
  const bills = new Map(db.allSessions().flatMap((s) => db.billsFor(s.id)).map((b) => [b.id, b]));
  const bill = (id) => bills.get(id);

  assert.equal(billCard(bill("old"), "2021"), undefined, "older bienniums keep the sitewide card");
  assert.equal(billCard(bill("ls"), "2025"), undefined, "LegiScan's bills keep the sitewide card");
  assert.deepEqual(billCard(bill("prev"), "2023 Regular Session"), {
    image: "/og/bills/2023/ab2.png",
    kicker: "Assembly Bill 2, 2023–24 session",
    title: "Parks",
    detail: "Vetoed",
    alt: "Assembly Bill 2, 2023–24 session. Parks. Vetoed.",
  });
  assert.equal(billCard(bill("sp"), "January 2026 Special Session").title, "Assembly Bill 1");
  assert.equal(personCard(db.people().find((p) => p.id === "gone")), undefined);
  assert.equal(personCard(db.people().find((p) => p.id === "rep")).detail, "Assembly District 12, Democrat");

  assert.deepEqual(shareCards().map((c) => c.image).sort(), [
    "/og/bills/2023/ab2.png",
    "/og/bills/2025/sb3.png",
    "/og/bills/2026s1/ab1.png",
    "/og/elections/2026/assembly-12.png",
    "/og/legislators/rep.png",
    "/og/legislators/sen.png",
  ]);
});
