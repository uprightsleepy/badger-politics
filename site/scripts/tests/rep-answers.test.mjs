import assert from "node:assert/strict";
import test from "node:test";
import { answers } from "../../src/lib/repAnswers.ts";

const ballotLine = (opponents) => {
  const full = {
    name: "Member", party: "Democratic", slug: "member", role: "Representative", contact: null,
    committees: [], attendance: { total: 0, missed: 0 }, voted: { cast: 0, total: 0 },
    authored: { total: 0, signedOn: 0, enacted: 0, vetoed: 0, noHearing: 0 },
    election: { cycle_year: 2026, on_ballot: 1 }, opponents, writeInPending: [], writeInReasons: [],
    loyalty: null, recentVotes: [],
  };
  const ctx = { house: "assembly", district: 1, typical: null, phase: "primary", general: "", mine: false };
  return answers(full, ctx).find((a) => a.id === "ballot").html;
};

test("ballot opponents join the way a sentence does", () => {
  assert.match(ballotLine([{ name: "Avery Lund", party: null }, { name: "Jordan Pike", party: null }]),
    /Avery Lund and Jordan Pike\./);
  assert.match(ballotLine([{ name: "Avery Lund", party: "Republican" }, { name: "Jordan Pike", party: "Independent" }]),
    /Avery Lund, a Republican, and Jordan Pike, an Independent\./);
  assert.match(ballotLine([{ name: "A", party: null }, { name: "B", party: null }, { name: "C", party: null }]),
    /A, B, and C\./);
});
