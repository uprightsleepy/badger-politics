import assert from "node:assert/strict";
import test from "node:test";
import { partySplitSentence, seatsSentence } from "../../src/lib/format.ts";

const party = (d, r, other = []) => [...Array(r).fill("Republican"), ...Array(d).fill("Democratic"), ...other];

test("seats: parties in alphabetical order, a majority only past half of all seats", () => {
  assert.equal(seatsSentence("Senate", 33, party(15, 18)),
    "Of the Senate's 33 seats, Democrats hold 15 and Republicans hold 18, a Republican majority.");
  assert.equal(seatsSentence("Assembly", 99, party(45, 54)),
    "Of the Assembly's 99 seats, Democrats hold 45 and Republicans hold 54, a Republican majority.");
  // vacancies count against a majority: 16 of 33 is not one
  assert.equal(seatsSentence("Senate", 33, party(15, 16)),
    "Of the Senate's 33 seats, Democrats hold 15 and Republicans hold 16.");
  assert.equal(seatsSentence("Senate", 33, party(17, 16)),
    "Of the Senate's 33 seats, Democrats hold 17 and Republicans hold 16, a Democratic majority.");
});

test("seats: singular members, independents and missing parties", () => {
  assert.equal(seatsSentence("Assembly", 99, party(45, 52, ["Independent"])),
    "Of the Assembly's 99 seats, Democrats hold 45, an independent holds 1, and Republicans hold 52, a Republican majority.");
  assert.equal(seatsSentence("Senate", 33, party(1, 2, [null])),
    "Of the Senate's 33 seats, a Democrat holds 1, Republicans hold 2, and a member with no party recorded holds 1.");
  assert.equal(seatsSentence("Senate", 33, []), "None of the Senate's 33 seats has a sitting member in our records.");
});

test("party split: same side, opposite sides, and even splits", () => {
  assert.equal(partySplitSentence({ dem: { yes: 14, no: 1 }, rep: { yes: 24, no: 0 } }),
    "Of members who voted yes or no, most of both parties voted yes: Democrats 14 yes and 1 no, Republicans 24 yes and 0 no.");
  assert.equal(partySplitSentence({ dem: { yes: 0, no: 35 }, rep: { yes: 2, no: 60 } }),
    "Of members who voted yes or no, most of both parties voted no: Democrats 0 yes and 35 no, Republicans 2 yes and 60 no.");
  assert.equal(partySplitSentence({ dem: { yes: 2, no: 33 }, rep: { yes: 62, no: 0 } }),
    "A party-line vote. Of members who voted yes or no, most Democrats voted no and most Republicans voted yes: Democrats 2 yes and 33 no, Republicans 62 yes and 0 no.");
  assert.equal(partySplitSentence({ dem: { yes: 5, no: 5 }, rep: { yes: 20, no: 3 } }),
    "Of members who voted yes or no: Democrats 5 yes and 5 no, Republicans 20 yes and 3 no. Democrats split evenly.");
  assert.equal(partySplitSentence({ dem: { yes: 1, no: 1 }, rep: { yes: 2, no: 2 } }),
    "Of members who voted yes or no: Democrats 1 yes and 1 no, Republicans 2 yes and 2 no. Both parties split evenly.");
});
