import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import Database from "better-sqlite3";
import ts from "typescript";
import { queries as fixtureQueries } from "./database.mjs";

const asModule = (source) => "data:text/javascript;base64," + Buffer.from(
  ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText,
).toString("base64");

test("state campaign totals require every month and keep federal/state identities separate", async () => {
  const directory = await mkdtemp(join(tmpdir(), "campaign-money-"));
  const file = join(directory, "test.sqlite");
  const db = new Database(file);
  db.exec(`CREATE TABLE meta (key TEXT,value TEXT);
    INSERT INTO meta VALUES ('imported_at','2025-03-10T00:00:00Z');
    CREATE TABLE state_campaigns (entity_id INTEGER,bioguide TEXT,candidate TEXT,office TEXT,
      cycle INTEGER,committee TEXT,source_url TEXT);
    INSERT INTO state_campaigns VALUES (10,'MEMBER','Pat Example','Wisconsin governor',2026,'Campaign','https://example.gov/10'),
      (11,NULL,'Other Candidate','Wisconsin governor',2026,'Other Campaign','https://example.gov/11');
    CREATE TABLE state_campaign_coverage (entity_id INTEGER,month TEXT);
    INSERT INTO state_campaign_coverage VALUES (10,'2025-01'),(10,'2025-03');
    CREATE TABLE state_campaign_transactions (filer_entity_id INTEGER,direction TEXT,date TEXT,
      amount REAL,other_entity_id INTEGER,other_name TEXT);
    INSERT INTO state_campaign_transactions VALUES
      (10,'INCOMING','2025-01-01',10.01,1,'Same Name'),
      (10,'INCOMING','2025-01-02',20.02,2,'Same Name'),
      (10,'OUTGOING','2025-03-01',5,3,'Vendor'),
      (11,'INCOMING','2025-02-01',999,1,'Unrelated campaign');`);
  const previous = process.env.WI_DATABASE_PATH;
  process.env.WI_DATABASE_PATH = file;
  const source = (await readFile(new URL("../../src/lib/db.ts", import.meta.url), "utf8"))
    .replace('"better-sqlite3"', JSON.stringify(pathToFileURL(createRequire(import.meta.url).resolve("better-sqlite3")).href))
    .replace('"./sentinels"', JSON.stringify(asModule(await readFile(new URL("../../src/lib/sentinels.ts", import.meta.url), "utf8"))));
  const queries = await import(asModule(source + "\nexport const closeTestDatabase = () => db.close();"));
  try {
    assert.deepEqual(queries.federalMoneyFor("MEMBER"), []);
    assert.deepEqual(queries.stateCampaignsFor("SOMEONE_ELSE"), []);
    let [campaign] = queries.stateCampaignsFor("MEMBER");
    assert.equal(campaign.complete, false, "a missing middle month cannot count as complete");
    assert.equal(campaign.totals, null, "partial money must not be presented as a total");
    assert.deepEqual(campaign.donors, []);
    db.exec("INSERT INTO state_campaign_coverage VALUES (10,'2025-02')");
    [campaign] = queries.stateCampaignsFor("MEMBER");
    assert.equal(campaign.complete, true);
    assert.equal(campaign.totals.receipts, 30.03);
    assert.equal(campaign.totals.spending, 5);
    assert.equal(campaign.donors.length, 2, "same-name contributors retain distinct source identities");
    const other = db.prepare("SELECT * FROM state_campaigns WHERE entity_id=11").get();
    assert.equal(queries.stateCampaignMoney(other).totals, null, "coverage belongs to each campaign");
    db.exec("INSERT INTO state_campaign_coverage VALUES (11,'2025-01'),(11,'2025-02'),(11,'2025-03')");
    const summary = queries.stateCampaignMoney(other);
    assert.equal(summary.complete, true);
    assert.equal(summary.totals.receipts, 999);
    assert.equal(summary.totals.spending, 0, "verified absence of spending is a real zero");
    assert.deepEqual(queries.stateCampaignsFor("MEMBER"), [campaign], "nonfederal campaigns stay off federal profiles");
    assert.equal(queries.stateCampaignMoney({ ...other, committee: "Wrong committee" }).totals, null);
    assert.equal(queries.stateCampaignMoney({ ...other, cycle: 2028 }).totals, null);
    assert.equal(queries.stateCampaignMoney({ ...other, entity_id: 12 }).totals, null, "new campaign on old snapshot stays pending");
  } finally {
    queries.closeTestDatabase();
    db.close();
    if (previous === undefined) delete process.env.WI_DATABASE_PATH;
    else process.env.WI_DATABASE_PATH = previous;
    await rm(directory, { recursive: true, force: true });
  }
});

test("curated campaigns remain visible as pending on snapshots without finance tables", () => {
  const db = new Database(":memory:");
  db.exec("CREATE TABLE meta (key TEXT,value TEXT); INSERT INTO meta VALUES ('imported_at','2026-09-10');");
  try {
    const queries = fixtureQueries(db);
    const campaign = queries.stateCampaignMoney({ entity_id: 12, candidate: "Example",
      office: "Wisconsin governor", cycle: 2026, committee: "Campaign", source_url: "https://example.gov/12" });
    assert.equal(campaign.candidate, "Example");
    assert.equal(campaign.complete, false);
    assert.equal(campaign.totals, null);
    assert.equal(campaign.months.length, 0);
    assert.equal(queries.stateCampaignsFor("MEMBER").length, 0);
  } finally {
    db.close();
  }
});
