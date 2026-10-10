import assert from "node:assert/strict";
import { test } from "node:test";
import { committeeFromReferral, plainHistory, sessionClosed, tellStory } from "../../src/lib/billStory.ts";

// docs.legis phrasing, trimmed to what each case needs
const a = (date, chamber, description, classification = "") => ({ date, chamber, description, classification });
const AFTER = "2026-10-09"; // the 2025 session's last voting day has passed
const DURING = "2025-10-20"; // the 2025 session is still moving bills
const bill = (status, extra = {}) => ({ session_id: "2025", chamber: "lower", classification: "bill", status, ...extra });
const here = (story) => story.stops.find((s) => s.state === "here");
const states = (story) => story.stops.map((s) => `${s.key}:${s.state}`).join(" ");

const introduced = [
  a("2025-11-19", "lower", "Introduced by Representatives Roe, Anderson; cosponsored by Senator Larson", "introduction"),
  a("2025-11-19", "lower", "Read first time and referred to Committee on Children and Families", "reading-1,referral-committee"),
];

test("a bill that died without a hearing stops in committee, not at introduction", () => {
  const actions = [
    ...introduced,
    a("2025-12-02", "lower", "Representative Tenorio added as a coauthor"),
    a("2026-01-14", "upper", "Senators Hesselbein and Roys added as cosponsors"),
    a("2026-03-23", "lower", "Failed to pass pursuant to Senate Joint Resolution 1"),
  ];
  const story = tellStory(bill("failed_sjr1"), actions, AFTER);
  assert.equal(story.headline, "Stopped in committee");
  assert.match(story.body.join(" "), /never got a \[\[public-hearing\|public hearing\]\]/);
  assert.match(story.body.join(" "), /last day for votes this session was Mar 19, 2026/);
  assert.equal(states(story), "introduced:done committee:here origin:todo other:todo governor:todo law:todo");
  assert.equal(here(story).note, "Stopped here. No public hearing was held.");
  assert.ok(story.stopped);
  assert.ok(story.terms.includes("sjr1"));
  assert.equal(story.progress.committee, "Assembly Committee on Children and Families");

  const history = plainHistory(bill("failed_sjr1"), actions);
  assert.deepEqual(history.map((e) => e.text), [
    "The session ended, and the bill died with it.",
    "1 more representative and 2 senators signed on in support.",
    "Sent to the Assembly Committee on Children and Families.",
    "Introduced in the Assembly.",
  ]);
  assert.equal(history[1].when, "Dec 2, 2025 to Jan 14, 2026");
});

test("the same bill while the session is open is waiting, not stopped", () => {
  const story = tellStory(bill("in_committee"), introduced, DURING);
  assert.equal(story.headline, "Waiting in committee");
  assert.equal(story.stopped, false);
  assert.equal(here(story).note, "Waiting for a public hearing.");
  assert.match(story.body[0], /^The Assembly Committee on Children and Families has it\./);
});

test("a hearing without a committee vote says so", () => {
  const story = tellStory(bill("failed_sjr1"), [
    ...introduced,
    a("2025-10-01", "lower", "Public hearing held"),
    a("2026-03-23", "lower", "Failed to pass pursuant to Senate Joint Resolution 1"),
  ], AFTER);
  assert.equal(story.headline, "Stopped in committee");
  assert.match(story.body[0], /had a \[\[public-hearing\|public hearing\]\] but no committee vote/);
  assert.equal(here(story).note, "Stopped here. It had a hearing but no committee vote.");
});

test("a committee recommendation without a floor vote stops before the full chamber", () => {
  const story = tellStory(bill("failed_sjr1"), [
    ...introduced,
    a("2025-10-01", "lower", "Public hearing held"),
    a("2025-10-08", "lower", "Executive action taken"),
    a("2025-10-09", "lower", "Report passage recommended by Committee on Children and Families, Ayes 9, Noes 0", "committee-passage-favorable"),
    a("2025-10-09", "lower", "Referred to committee on Rules", "referral-committee"),
    a("2026-03-23", "lower", "Failed to pass pursuant to Senate Joint Resolution 1"),
  ], AFTER);
  assert.equal(story.headline, "Stopped before the full Assembly voted");
  assert.equal(states(story), "introduced:done committee:done origin:here other:todo governor:todo law:todo");
  // the policy committee, not Rules, is the bill's committee
  assert.equal(story.progress.committee, "Assembly Committee on Children and Families");
});

test("passing one chamber then dying names both chambers", () => {
  const actions = [
    ...introduced,
    a("2025-10-14", "lower", "Read a third time and passed, Ayes 60, Noes 35", "passage"),
    a("2025-10-15", "upper", "Received from Assembly", "introduction"),
    a("2025-10-15", "upper", "Read first time and referred to committee on Health", "reading-1,referral-committee"),
    a("2026-03-23", "upper", "Failed to concur in pursuant to Senate Joint Resolution 1"),
  ];
  const story = tellStory(bill("failed_sjr1"), actions, AFTER);
  assert.equal(story.headline, "Passed the Assembly, then stopped");
  assert.equal(here(story).key, "other");
  assert.equal(story.stops.find((s) => s.key === "origin").detail, "Passed 60 to 35");
  const history = plainHistory(bill("failed_sjr1"), actions).map((e) => e.text);
  assert.ok(history.includes("The Assembly passed it, 60 to 35."));
  assert.ok(history.includes("Sent to the Senate Committee on Health."));
});

test("a veto and a failed override", () => {
  const story = tellStory(bill("vetoed"), [
    ...introduced,
    a("2025-06-03", "lower", "Read a third time and passed, Ayes 54, Noes 44", "passage"),
    a("2025-06-24", "upper", "Read a third time and concurred in, Ayes 18, Noes 14", "passage"),
    a("2025-07-01", "lower", "Presented to the Governor on 7-1-2025", "executive-receipt"),
    a("2025-07-08", "lower", "Report vetoed by the Governor on 7-8-2025", "executive-veto"),
    a("2026-05-13", "lower", "Failed to pass notwithstanding the objections of the Governor pursuant to Joint Rule 82, Ayes 54, Noes 45"),
  ], AFTER);
  assert.equal(story.headline, "Vetoed by the governor");
  assert.equal(here(story).key, "governor");
  assert.equal(here(story).note, "Vetoed Jul 8, 2025.");
  assert.match(story.body.join(" "), /tried to \[\[veto-override\|override the veto\]\] on May 13, 2026, but fell short/);
});

test("a law signed with a partial veto names its act", () => {
  const story = tellStory(bill("enacted"), [
    a("2025-02-18", "lower", "Introduced by Joint Committee on Finance, by request of Governor", "introduction"),
    a("2025-07-02", "lower", "Read a third time and passed, Ayes 50, Noes 45", "passage"),
    a("2025-07-02", "upper", "Read a third time and concurred in, Ayes 18, Noes 15", "passage"),
    a("2025-07-03", "lower", "Report approved by the Governor with partial veto on 7-3-2025. 2025 Wisconsin Act 15", "executive-signature,executive-veto-line-item"),
  ], AFTER);
  assert.equal(story.headline, "Became law");
  assert.ok(story.progress.partialVeto);
  assert.equal(story.progress.act, "2025 Wisconsin Act 15");
  assert.equal(here(story).key, "law");
  assert.equal(here(story).note, "2025 Wisconsin Act 15");
  assert.ok(story.stops.every((s) => s.state !== "todo"));
});

test("passed both chambers waits for the governor even after the session", () => {
  const story = tellStory(bill("passed"), [
    ...introduced,
    a("2026-02-10", "lower", "Read a third time and passed", "passage"),
    a("2026-03-19", "upper", "Read a third time and concurred in", "passage"),
  ], AFTER);
  assert.equal(story.headline, "Waiting for the governor");
  assert.equal(story.stopped, false);
  assert.equal(here(story).key, "governor");
});

test("a joint resolution ends at adoption and never reaches the governor", () => {
  const story = tellStory(bill("adopted", { classification: "joint resolution" }), [
    a("2025-04-20", "lower", "Introduced by Representative Smith", "introduction"),
    a("2025-05-13", "lower", "Adopted", "passage"),
    a("2025-05-15", "upper", "Concurred in", "passage"),
  ], AFTER);
  assert.equal(story.headline, "Adopted");
  assert.deepEqual(story.stops.map((s) => s.key), ["introduced", "origin", "other", "adopted"]);
  assert.ok(!story.stops.some((s) => s.key === "governor"));
});

test("unfamiliar entries keep the Legislature's own wording; housekeeping is left to the record", () => {
  const history = plainHistory(bill("in_committee"), [
    ...introduced,
    a("2025-12-01", "lower", "Placed on calendar 12-2-2025 by Committee on Rules"),
    a("2025-12-02", "lower", "Point of order that Assembly Bill 9 was not properly before the Assembly not well taken"),
  ]);
  assert.equal(history[0].official, true);
  assert.match(history[0].text, /^Point of order/);
  assert.ok(!history.some((e) => /calendar/i.test(e.text)));
});

test("committee names drop procedural tails", () => {
  assert.equal(
    committeeFromReferral("Withdrawn from committee on Senate Organization and rereferred to committee on Education pursuant to Senate Rule 46(2)(c)", "upper"),
    "Senate Committee on Education",
  );
  assert.equal(committeeFromReferral("Read first time and referred to joint committee on Finance", "lower"), "Joint Committee on Finance");
  assert.equal(committeeFromReferral("Referred to calendar of 2-20-2025", "lower"), null);
});

test("past sessions are closed; the current one closes after its last voting day", () => {
  assert.equal(sessionClosed("2023", "2024-01-10"), true);
  assert.equal(sessionClosed("2025", "2026-03-19"), false);
  assert.equal(sessionClosed("2025", "2026-03-20"), true);
});
