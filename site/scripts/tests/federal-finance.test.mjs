import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import Database from "better-sqlite3";
import ts from "typescript";

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
    INSERT INTO state_campaigns VALUES (10,'MEMBER','Pat Example','Wisconsin governor',2026,'Campaign','https://example.gov/10');
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
    db.exec("INSERT INTO state_campaign_coverage VALUES (10,'2025-02')");
    [campaign] = queries.stateCampaignsFor("MEMBER");
    assert.equal(campaign.complete, true);
    assert.equal(campaign.totals.receipts, 30.03);
    assert.equal(campaign.totals.spending, 5);
    assert.equal(campaign.donors.length, 2, "same-name contributors retain distinct source identities");
  } finally {
    queries.closeTestDatabase();
    db.close();
    if (previous === undefined) delete process.env.WI_DATABASE_PATH;
    else process.env.WI_DATABASE_PATH = previous;
    await rm(directory, { recursive: true, force: true });
  }
});
