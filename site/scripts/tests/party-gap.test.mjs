import assert from "node:assert/strict";
import test from "node:test";
import { partyGapSentence } from "../../src/lib/format.ts";

test("names the members party totals leave out, by party in alphabetical order", () => {
  assert.equal(
    partyGapSentence([
      { party: "Republican", sitting: 33, covered: 29 },
      { party: "Democratic", sitting: 21, covered: 19 },
    ]),
    "These totals leave out 6 sitting legislators whose receipts we haven't collected: 2 Democrats and 4 Republicans.",
  );
});

test("singular forms and parties with no gap", () => {
  assert.equal(
    partyGapSentence([
      { party: "Democratic", sitting: 21, covered: 20 },
      { party: "Republican", sitting: 33, covered: 33 },
    ]),
    "These totals leave out 1 sitting legislator whose receipts we haven't collected: 1 Democrat.",
  );
});

test("three groups take a serial comma; a missing party is named as such", () => {
  assert.equal(
    partyGapSentence([
      { party: "Democratic", sitting: 21, covered: 20 },
      { party: null, sitting: 1, covered: 0 },
      { party: "Republican", sitting: 33, covered: 31 },
    ]),
    "These totals leave out 4 sitting legislators whose receipts we haven't collected: 1 Democrat, 2 Republicans, and 1 with no party recorded.",
  );
});

test("full coverage needs no sentence", () => {
  assert.equal(partyGapSentence([{ party: "Republican", sitting: 33, covered: 33 }]), null);
  assert.equal(partyGapSentence([]), null);
});
