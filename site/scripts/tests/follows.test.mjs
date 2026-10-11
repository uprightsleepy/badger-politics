import assert from "node:assert/strict";
import test from "node:test";
import {
  decodeFollows, encodeFollows, followsOpml, getFollows, heardSince, isNewSince, lastSeen, markSeen,
  mergeFollows, splitBillId, toggleFollow,
} from "../../src/scripts/follows.ts";
import { forgetDistrict, saveDistrict, savedDistrict } from "../../src/lib/district.ts";
import { savedCityDistrict } from "../../src/lib/cityDistrict.ts";
import { savedPollingPlace } from "../../src/lib/pollingPlace.ts";
import { wisconsinToday } from "../../src/lib/today.ts";

test("today is Wisconsin's date, not UTC's, on either side of midnight", () => {
  // 9:30 PM CDT is already the next day in UTC
  assert.equal(wisconsinToday(new Date("2026-10-12T02:30:00Z")), "2026-10-11");
  assert.equal(wisconsinToday(new Date("2026-10-12T05:30:00Z")), "2026-10-12");
  // CST in winter: 6 hours behind
  assert.equal(wisconsinToday(new Date("2026-01-02T05:59:00Z")), "2026-01-01");
});

test("an evening visit still sees the next day's action as new", () => {
  const seen = wisconsinToday(new Date("2026-10-12T02:30:00Z"));
  assert.equal(isNewSince(seen, "2026-10-12"), true);
  assert.equal(isNewSince(seen, "2026-10-11"), false, "the visit's own day was already seen");
  assert.equal(isNewSince(null, "2026-10-12"), false, "a first visit has nothing to compare");
  assert.equal(isNewSince(seen, null), false);
});

test("a committee is new for a hearing held since the visit, not one still ahead", () => {
  assert.equal(heardSince("2026-10-01", ["2026-09-30", "2026-10-20"], "2026-10-11"), false);
  assert.equal(heardSince("2026-10-01", ["2026-10-05"], "2026-10-11"), true);
  assert.equal(heardSince("2026-10-01", ["2026-10-11"], "2026-10-11"), false, "today's hearing may not have happened");
});

test("blocked storage remembers nothing and throws nothing", (t) => {
  // what a browser with site data blocked does on any access
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() { throw new DOMException("blocked", "SecurityError"); },
  });
  t.after(() => delete globalThis.localStorage);
  assert.equal(savedDistrict(), null);
  saveDistrict({ ad: 1, sd: 1 });
  forgetDistrict();
  assert.equal(savedCityDistrict(), null);
  assert.equal(savedPollingPlace(), null);
  assert.equal(toggleFollow("bills", "2025-ab1"), true);
  assert.deepEqual(getFollows().bills, []);
  markSeen();
  assert.equal(lastSeen(), null);
});

test("a bill id splits at its last hyphen, so special sessions keep theirs", () => {
  assert.deepEqual(splitBillId("2013s-dec-ab1"), { session: "2013s-dec", slug: "ab1" });
  assert.deepEqual(splitBillId("2025-ab656"), { session: "2025", slug: "ab656" });
});

const sample = {
  bills: ["2025-ab1", "2013s-dec-ab1"], legislators: ["romaine-quinn"], committees: [],
  districts: ["senate-5"], races: ["assembly-99"], council: ["milwaukee/jane-doe"],
};

test("a follow list survives the trip through a share link", () => {
  const text = encodeFollows(sample);
  assert.equal(text, "bills:2025-ab1,2013s-dec-ab1;legislators:romaine-quinn;districts:senate-5;races:assembly-99;council:milwaukee/jane-doe");
  assert.deepEqual(decodeFollows(text), sample);
  // a messenger that percent-encodes the fragment changes nothing
  assert.deepEqual(decodeFollows(encodeURIComponent(text)), sample);
});

test("a share link with anything malformed is rejected whole", () => {
  for (const bad of [
    "",
    "bills",
    "pets:rex",
    "__proto__:x",
    "bills:2025-ab1;bills:2025-ab2",
    "bills:2025-ab1,",
    "bills:<script>",
    "legislators:../../api",
    "legislators:Romaine-Quinn",
    "districts:senate-100",
    "races:house-5",
    "council:milwaukee",
    "council:a/b/c",
    "%E0%A4%A",
    `bills:${Array.from({ length: 501 }, (_, i) => `2025-ab${i}`).join(",")}`,
  ]) {
    assert.equal(decodeFollows(bad), null, bad.slice(0, 40));
  }
  assert.deepEqual(decodeFollows("bills:2025-ab1,2025-ab1").bills, ["2025-ab1"], "duplicates collapse");
});

test("a stored id that wouldn't validate is left out of the link", () => {
  const empty = { bills: [], legislators: [], committees: [], districts: [], races: [], council: [] };
  assert.equal(encodeFollows({ ...empty, bills: ["2025-ab1", "javascript:alert(1)"] }), "bills:2025-ab1");
  assert.equal(encodeFollows(empty), "");
});

test("importing merges into what's already followed", (t) => {
  const data = new Map();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: (k) => data.delete(k) },
  });
  t.after(() => delete globalThis.localStorage);
  toggleFollow("bills", "2025-ab1");
  assert.equal(mergeFollows(sample), 5, "the one already followed is not new");
  assert.deepEqual(getFollows().bills, ["2025-ab1", "2013s-dec-ab1"]);
  assert.equal(mergeFollows(sample), 0);
});

test("OPML lists a feed for each followed kind that has one, names escaped", () => {
  const opml = followsOpml(sample, "https://badgerpolitics.org", new Map([["bills|2025-ab1", "AB 1 & friends"]]));
  assert.match(opml, /<outline type="rss" text="AB 1 &amp; friends" title="AB 1 &amp; friends" xmlUrl="https:\/\/badgerpolitics.org\/feeds\/bills\/2025-ab1.xml"\/>/);
  assert.match(opml, /xmlUrl="https:\/\/badgerpolitics.org\/feeds\/legislators\/romaine-quinn.xml"/);
  assert.match(opml, /xmlUrl="https:\/\/badgerpolitics.org\/feeds\/local\/milwaukee\/jane-doe.xml"/);
  assert.doesNotMatch(opml, /senate-5|assembly-99|Committees/, "districts, races and empty kinds have no feed");
});
