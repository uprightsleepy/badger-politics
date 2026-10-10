/** The glossary: the single source of every definition on the site.
 *
 * GLOSSARY holds the full entries the glossary page lists. TERMS holds the
 * short, plain definitions that pages show inline ("Terms on this page"
 * and the popovers behind dotted-underlined words). Each short term points
 * at the glossary entry that carries the official wording. */

export interface GlossaryEntry {
  /** Stable anchor on /glossary/, e.g. /glossary/#public-hearing */
  id: string;
  term: string;
  definition: string;
}

export const GLOSSARY: GlossaryEntry[] = [
  { id: "biennium", term: "Biennium / biennial session", definition: "The Legislature's two-year working period, starting in January of each odd-numbered year. Bills live and die within one biennium; nothing carries over." },
  { id: "floorperiod", term: "Floorperiod", definition: "A scheduled stretch of days when a chamber meets to debate and vote on bills. The schedule is set at the session's start by joint resolution." },
  { id: "readings", term: "First / second / third reading", definition: "The three formal stages of a bill on the floor. Amendments happen at second reading; final passage is the vote on third reading." },
  { id: "referral", term: "Referral", definition: "Assignment of a new bill to a committee. Most bills never leave the committee they're referred to." },
  { id: "public-hearing", term: "Public hearing", definition: "A committee meeting where anyone may register or testify on a bill. Getting one is the first hurdle most bills fail: see Bills that never got a hearing." },
  { id: "executive-session", term: "Executive session", definition: "A committee's voting meeting, open to the public despite the name. The committee votes on whether to recommend the bill; no public testimony is taken." },
  { id: "appearance-slip", term: "Appearance slip", definition: "The form you fill out at a hearing to register for, against, or for-information-only on a bill, with or without speaking." },
  { id: "fiscal-estimate", term: "Fiscal estimate", definition: "A state agency's projection of what a bill would cost or save, attached to the bill. Linked on bill pages here when one exists." },
  { id: "lrb-analysis", term: "LRB analysis", definition: "The Legislative Reference Bureau's neutral plain-language summary printed at the top of most bills. Shown on bill pages here, verbatim." },
  { id: "amendment", term: "Amendment / substitute amendment", definition: "A change to a bill's text; a substitute amendment replaces the whole text. Both are voted on before final passage." },
  { id: "engrossment", term: "Engrossment", definition: "The official incorporation of adopted amendments into a bill's text before it moves on." },
  { id: "author", term: "Author, coauthor, cosponsor", definition: "The legislator who introduces a bill is its author, and the first name printed on the bill is its lead author. Members of the same house who sign on are coauthors; members of the other house are cosponsors. A bill's \"Introduced by\" line often runs to dozens of names, so being on it is not the same as leading the bill, and none of these roles means writing the text, which the Legislative Reference Bureau drafts." },
  { id: "concurrence", term: "Concurrence", definition: "One chamber's approval of the other chamber's bill. A bill must pass both chambers in identical form before it can go to the governor." },
  { id: "passage", term: "Passage", definition: "The vote that actually decides a bill: passage in its house of origin, concurrence in the other house. It needs a simple majority of members voting." },
  { id: "suspension-of-the-rules", term: "Suspension of the rules", definition: "A procedural vote to skip the normal schedule, most often to take up a bill's third reading immediately. It needs a two-thirds majority, a higher bar than passing the bill itself, so a suspension motion can draw more Ayes than the passage vote that follows it, and tallies shift between motions as members come and go from the floor." },
  { id: "tabled", term: "Tabled / laid on table", definition: "A motion that sets a bill or amendment aside, usually permanently. A quiet way to kill something without a direct vote against it." },
  { id: "joint-resolution", term: "Joint resolution", definition: "A measure passed by both chambers that doesn't go to the governor: session schedules, constitutional amendments, and honors." },
  { id: "failed-to-pass-pursuant-to-sjr-1", term: "Failed to pass pursuant to SJR 1", definition: "The end of the road for most bills: Senate Joint Resolution 1 sets the session's last day for general business, and every bill still pending on that day formally fails." },
  { id: "enrolled", term: "Enrolled", definition: "The final, authoritative copy of a measure after passage, as sent to the governor or secretary of state." },
  { id: "act", term: "Act", definition: "What a bill becomes when the governor signs it (or a veto is overridden): a numbered Wisconsin Act, part of state law." },
  { id: "partial-veto", term: "Partial veto", definition: "Wisconsin's unusually strong line-item veto: the governor can strike words and numbers within appropriation bills, changing their meaning. Subject to override like a full veto." },
  { id: "veto-override", term: "Veto override", definition: "The Legislature's power to enact a bill over the governor's veto. It takes a two-thirds vote in each chamber. The governor's decisions page lists every attempt." },
  { id: "roll-call-vote", term: "Roll call vote", definition: "A vote where each member's Aye or Nay is recorded by name. Only roll calls appear in attendance and vote records here; voice votes record no names." },
  { id: "voice-vote", term: "Voice vote", definition: "A vote by collective shout, recorded only as the outcome. No individual positions exist, so none are shown here." },
  { id: "votes-with-party", term: "Votes with party majority", definition: "How often a member's Aye or Nay matched the position most of their own party took on the same roll call, shown on member pages here. Roll calls where their party split evenly, and votes they didn't cast, aren't counted." },
  { id: "party-line", term: "Party-line / bipartisan vote", definition: "As described on roll calls here: party-line means most Democrats and most Republicans voted opposite ways; when most of both parties vote the same way, the page says so. Members who didn't vote yes or no aren't counted, and a party split evenly takes neither side." },
  { id: "special-session", term: "Special session", definition: "A session called by the governor, limited to subjects in the call. Special-session bills carry their own numbering." },
  { id: "extraordinary-session", term: "Extraordinary session", definition: "A session the Legislature calls itself, outside the scheduled floorperiods." },
  { id: "recall-election", term: "Recall election", definition: "A mid-term election to remove a sitting legislator, triggered by petition. Recalls in 2011 and 2012 changed several Senate seats; those departures are labeled on the profiles here." },
  { id: "sine-die", term: "Sine die", definition: "Adjournment “without a day”: the formal close of the biennial session period." },
];

export interface Term {
  /** What we call it on the page, in sentence case. */
  label: string;
  /** One plain sentence (two at most). Grade 8 or below. */
  short: string;
  /** The Legislature's own name for it, when that differs. */
  official?: string;
  /** Glossary entry with the full definition. */
  glossary: string;
}

export const TERMS = {
  committee: {
    label: "Committee",
    short: "A small group of lawmakers that looks at a bill first. Most bills never leave committee.",
    glossary: "referral",
  },
  "public-hearing": {
    label: "Public hearing",
    short: "A meeting where anyone can speak to a committee about a bill, or send written comments.",
    glossary: "public-hearing",
  },
  "committee-vote": {
    label: "Committee vote",
    short: "The committee's own vote on whether to recommend the bill to the full chamber.",
    official: "Executive session",
    glossary: "executive-session",
  },
  sjr1: {
    label: "Senate Joint Resolution 1",
    short: "The session's calendar. Any bill not passed by its last voting day dies.",
    official: "Failed to pass pursuant to SJR 1",
    glossary: "failed-to-pass-pursuant-to-sjr-1",
  },
  author: {
    label: "Author",
    short: "A lawmaker who formally puts a bill forward. The text itself is drafted by the Legislative Reference Bureau.",
    official: "Author, coauthor",
    glossary: "author",
  },
  cosponsor: {
    label: "Signed on in support",
    short: "Lawmakers who back a bill without being one of its authors, often from the other chamber.",
    official: "Cosponsor",
    glossary: "author",
  },
  lrb: {
    label: "Legislative Reference Bureau",
    short: "The Legislature's nonpartisan office that drafts bills and writes the summary at the top of each one.",
    official: "LRB analysis",
    glossary: "lrb-analysis",
  },
  "second-chamber": {
    label: "Second chamber's vote",
    short: "A bill has to pass both the Assembly and the Senate in the same form before it goes to the governor.",
    official: "Concurrence",
    glossary: "concurrence",
  },
  act: {
    label: "Wisconsin Act",
    short: "The number a bill gets when it becomes law, like 2025 Wisconsin Act 12.",
    official: "Act",
    glossary: "act",
  },
  "veto-override": {
    label: "Veto override",
    short: "Lawmakers can still pass a bill the governor vetoed, but it takes two-thirds of each chamber.",
    glossary: "veto-override",
  },
  "partial-veto": {
    label: "Partial veto",
    short: "Wisconsin's governor can strike parts of a budget bill and sign the rest into law.",
    glossary: "partial-veto",
  },
  "roll-call": {
    label: "Roll call",
    short: "A vote where each lawmaker's yes or no is recorded by name.",
    official: "Roll call vote",
    glossary: "roll-call-vote",
  },
  "fiscal-estimate": {
    label: "Cost estimate",
    short: "A state agency's estimate of what a bill would cost or save.",
    official: "Fiscal estimate",
    glossary: "fiscal-estimate",
  },
  "with-party": {
    label: "Voting with their party",
    short: "How often a lawmaker's yes or no matched what most of their own party voted on the same roll call.",
    glossary: "votes-with-party",
  },
  "joint-resolution": {
    label: "Joint resolution",
    short: "A measure both chambers pass that doesn't go to the governor, such as a schedule or an honor.",
    glossary: "joint-resolution",
  },
} satisfies Record<string, Term>;

export type TermId = keyof typeof TERMS;
