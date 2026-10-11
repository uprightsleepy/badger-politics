import assert from "node:assert/strict";
import test from "node:test";
import { mapsNote } from "../../src/lib/ballot.ts";

test("each result before 2024 names the maps it was held under", () => {
  assert.equal(mapsNote(2024), null, "today's maps carry no note");
  assert.equal(mapsNote(2026), null);
  assert.equal(mapsNote(2022), "2022 maps");
  assert.equal(mapsNote(2020), "2011 maps");
  assert.equal(mapsNote(2014), "2011 maps");
});
