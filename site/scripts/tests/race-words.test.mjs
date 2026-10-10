import assert from "node:assert/strict";
import test from "node:test";
import { nameList, raceSentenceHtml, resultSentence, withParty } from "../../src/lib/ballot.ts";

const holder = { name: "Dana Whitfield", party: "Democratic", href: "/legislators/dana-whitfield/" };
const link = '<a href="/legislators/dana-whitfield/" class="underline">Dana Whitfield</a>';

test("names with parties join with commas, and semicolons from three on", () => {
  assert.equal(withParty("Jordan Pike", "Republican"), "Jordan Pike, a Republican");
  assert.equal(withParty("Sol Weber", "Independent"), "Sol Weber, an Independent");
  assert.equal(nameList(["A", "B"]), "A and B");
  assert.equal(nameList(["A, a Democrat", "B, a Republican"]), "A, a Democrat, and B, a Republican");
  assert.equal(nameList(["A, a Democrat", "B, a Republican", "C, an Independent"]), "A, a Democrat; B, a Republican; and C, an Independent");
});

test("a contested race names the incumbent and the challengers", () => {
  assert.equal(
    raceSentenceHtml({ holder, status: "on-ballot", others: [{ name: "Jordan Pike", party: "Republican" }], phase: "general" }),
    `${link}, the Democratic incumbent, faces Jordan Pike, a Republican.`,
  );
  assert.equal(
    raceSentenceHtml({ holder, status: "on-ballot", others: [], phase: "general" }),
    `${link}, the Democratic incumbent, is running unopposed.`,
  );
  assert.equal(
    raceSentenceHtml({ holder, status: "on-ballot", others: [], phase: "primary" }),
    `${link}, the Democratic incumbent, is the only approved candidate so far.`,
  );
});

test("an open seat says who isn't running and who is", () => {
  assert.equal(
    raceSentenceHtml({
      holder, status: "not-running", phase: "general",
      others: [{ name: "Riley Stroud", party: "Republican" }, { name: "Jordan Pike", party: "Democratic" }],
    }),
    `${link}, the Democratic incumbent, isn't on the ballot. Riley Stroud, a Republican, and Jordan Pike, a Democrat, are on the ballot.`,
  );
  assert.equal(
    raceSentenceHtml({ holder, status: "not-running", phase: "general", others: [] }),
    `${link}, the Democratic incumbent, isn't on the ballot. No candidate is on the ballot for this seat.`,
  );
});

test("a pending status is never read as a retirement", () => {
  assert.equal(
    raceSentenceHtml({ holder, status: "pending", phase: "primary", others: [{ name: "Jo Moe", party: null }] }),
    `The Elections Commission hasn't posted whether ${link} is running. Jo Moe is approved for the ballot.`,
  );
});

test("names are escaped", () => {
  assert.match(
    raceSentenceHtml({ holder: { name: "<b>X</b>", party: null }, status: "on-ballot", others: [], phase: "general" }),
    /^&lt;b&gt;X&lt;\/b&gt;, the incumbent,/,
  );
});

test("results: winners, tickets, ties and unopposed races", () => {
  assert.equal(
    resultSentence([{ candidate: "Dana Whitfield", party: "Democratic", votes: 17512 }, { candidate: "Gerald Okafor", party: "Republican", votes: 15041 }], 32640),
    "Dana Whitfield, a Democrat, won with 53.7% of 32,640 votes cast.",
  );
  assert.equal(
    resultSentence([{ candidate: "Alden Marsh / Nadia Price", party: "Democratic", votes: 1358774 }, { candidate: "Tim Rowe / Rae Kline", party: "Republican", votes: 1268535 }], 2653418),
    "The Democratic ticket of Alden Marsh and Nadia Price won with 51.2% of 2,653,418 votes cast.",
  );
  assert.equal(
    resultSentence([{ candidate: "A B", party: "Democratic", votes: 10 }, { candidate: "C D", party: "Republican", votes: 10 }], 20),
    "A B, a Democrat, and C D, a Republican, tied with 10 votes each.",
  );
  assert.equal(
    resultSentence([{ candidate: "Gerald Okafor", party: "Republican", votes: 21007 }], 21212),
    "Gerald Okafor, a Republican, ran unopposed and got 21,007 of 21,212 votes cast.",
  );
});
