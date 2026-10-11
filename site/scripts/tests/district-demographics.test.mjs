import assert from "node:assert/strict";
import { test } from "node:test";
import Database from "better-sqlite3";
import { queries as fixtureQueries } from "./database.mjs";

test("district figures appear only for a release on the current map", () => {
  const db = new Database(":memory:");
  try {
    let queries = fixtureQueries(db);
    assert.equal(queries.districtDemographicsFor("lower", 15), null, "older snapshots have no table");
    db.exec(`CREATE TABLE district_demographics (chamber TEXT, district INTEGER, acs_year INTEGER,
        map_year INTEGER, measure TEXT, estimate REAL, moe REAL);
      INSERT INTO district_demographics VALUES
        ('lower', 15, 2024, 2024, 'population', 59500, 1800),
        ('lower', 15, 2024, 2024, 'median_age', 41.2, 1.1),
        ('lower', 16, 2023, 2022, 'population', 58000, 1700);`);
    queries = fixtureQueries(db);
    assert.deepEqual(queries.districtDemographicsFor("lower", 15), {
      acsYear: 2024,
      figures: { population: { estimate: 59500, moe: 1800 }, median_age: { estimate: 41.2, moe: 1.1 } },
    });
    assert.equal(queries.districtDemographicsFor("lower", 16), null, "2022-map figures never sit beside 2024 lines");
    assert.equal(queries.districtDemographicsFor("upper", 15), null);
  } finally {
    db.close();
  }
});
