import assert from "node:assert/strict";
import test from "node:test";
import { committeeTitle } from "../../src/lib/format.ts";

test("chamber committees take the Legislature's full form", () => {
  assert.equal(committeeTitle("Education", "lower"), "Assembly Committee on Education");
  assert.equal(committeeTitle("Health", "upper"), "Senate Committee on Health");
  assert.equal(committeeTitle("Assembly Organization", "lower"), "Assembly Committee on Assembly Organization");
  assert.equal(committeeTitle("Committee on Rules", "lower"), "Assembly Committee on Rules");
});

test("joint committees and self-named bodies keep their own names", () => {
  assert.equal(committeeTitle("Joint Committee on Finance", null), "Joint Committee on Finance");
  assert.equal(committeeTitle("Speaker's Task Force on Suicide Prevention", "lower"), "Speaker's Task Force on Suicide Prevention");
  assert.equal(committeeTitle("Joint Legislative Council", null), "Joint Legislative Council");
  assert.equal(committeeTitle("Senate Committee on Labor", "upper"), "Senate Committee on Labor");
});
