import PERSON_SLUGS from "../data/person-slugs.json" with { type: "json" };

export const STATUS_LABELS: Record<string, string> = {
  introduced: "Introduced",
  in_committee: "In committee",
  passed_chamber: "Passed one chamber",
  passed: "Passed both chambers",
  adopted: "Adopted",
  enacted: "Became law",
  vetoed: "Vetoed",
  failed_sjr1: "Died at session end",
};

/** Status in plain words for lists of bills (docs/brand.md, "Status
 * wording"). STATUS_LABELS stays as is: it is also a search facet value. */
export const STATUS_PLAIN: Record<string, string> = {
  introduced: "Introduced",
  in_committee: "In committee",
  passed_chamber: "Passed one chamber",
  passed: "Passed both chambers",
  adopted: "Adopted",
  enacted: "Became law",
  vetoed: "Vetoed",
  failed_sjr1: "Stopped when the session ended",
};

/** "Democratic" (the party's name) -> "Democrat" (what a member is). */
export const partyWord = (party: string | null): string =>
  party === "Democratic" ? "Democrat" : (party ?? "Party not recorded");

/** "Democratic" -> "Democrats"; for counts in sentences. */
export const partyPlural = (party: string): string =>
  party === "Democratic"
    ? "Democrats"
    : party === "Republican"
      ? "Republicans"
      : /^independent$/i.test(party)
        ? "independents"
        : `${party} members`;

const IDENT_WORDS: Record<string, string> = {
  AB: "Assembly Bill",
  SB: "Senate Bill",
  AJR: "Assembly Joint Resolution",
  SJR: "Senate Joint Resolution",
  AR: "Assembly Resolution",
  SR: "Senate Resolution",
};
/** "AB 656" -> "Assembly Bill 656". Unknown prefixes stay as printed. */
export const identifierLong = (identifier: string): string => {
  const m = /^([A-Z]+)\s*(\d+)$/.exec(identifier.trim());
  return m && IDENT_WORDS[m[1]] ? `${IDENT_WORDS[m[1]]} ${m[2]}` : identifier;
};

/** "2025" -> "2025–26 session"; special sessions keep their own name. */
export const sessionPlainName = (sessionId: string, name: string): string =>
  /^\d{4}$/.test(sessionId)
    ? `${sessionId}–${String((Number(sessionId) + 1) % 100).padStart(2, "0")} session`
    : name;

/** Party order for lists: alphabetical, with no party recorded last. */
export const byPartyName = (a: { party: string | null }, b: { party: string | null }): number =>
  a.party == null ? (b.party == null ? 0 : 1) : b.party == null ? -1 : a.party.localeCompare(b.party);

/** Who party totals leave out: sitting members whose receipts we haven't
 * collected, counted by party ("…: 2 Democrats and 4 Republicans."). Null
 * when every sitting member is covered. Parties in alphabetical order,
 * never by size. */
export const partyGapSentence = (
  rows: { party: string | null; sitting: number; covered: number }[],
): string | null => {
  const gaps = rows
    .map((r) => ({ party: r.party, n: r.sitting - r.covered }))
    .filter((g) => g.n > 0)
    .sort(byPartyName);
  const total = gaps.reduce((sum, g) => sum + g.n, 0);
  if (!total) return null;
  const parts = gaps.map((g) =>
    g.party ? `${g.n} ${g.n === 1 ? partyWord(g.party) : partyPlural(g.party)}` : `${g.n} with no party recorded`,
  );
  const list = parts.length <= 2 ? parts.join(" and ") : `${parts.slice(0, -1).join(", ")}, and ${parts.at(-1)}`;
  return `These totals leave out ${total} sitting ${total === 1 ? "legislator" : "legislators"} whose receipts we haven't collected: ${list}.`;
};

/** Who holds a chamber's seats, parties in alphabetical order, never by
 * size: "Of the Senate's 33 seats, Democrats hold 15 and Republicans hold
 * 18, a Republican majority." A majority is named only when one party
 * holds more than half of all the seats, vacancies included. */
export const seatsSentence = (chamber: string, seats: number, parties: (string | null)[]): string => {
  const counts = new Map<string | null, number>();
  for (const p of parties) counts.set(p, (counts.get(p) ?? 0) + 1);
  const rows = [...counts].map(([party, n]) => ({ party, n })).sort(byPartyName);
  const subject = ({ party, n }: { party: string | null; n: number }) => {
    if (!party) return n === 1 ? "a member with no party recorded" : "members with no party recorded";
    if (n > 1) return partyPlural(party);
    const word = /^independent$/i.test(party) ? "independent" : partyWord(party);
    return `${/^[aeiou]/i.test(word) ? "an" : "a"} ${word}`;
  };
  const parts = rows.map((r) => `${subject(r)} ${r.n === 1 ? "holds" : "hold"} ${r.n.toLocaleString()}`);
  const list = parts.length <= 2 ? parts.join(" and ") : `${parts.slice(0, -1).join(", ")}, and ${parts.at(-1)}`;
  const major = rows.find((r) => r.party && r.n * 2 > seats);
  const majority = major ? `, a ${major.party} majority` : "";
  if (!parts.length) return `None of the ${chamber}'s ${seats} seats has a sitting member in our records.`;
  return `Of the ${chamber}'s ${seats} seats, ${list}${majority}.`;
};

/** A roll call's party split in words, Democrats before Republicans (the
 * alphabet, not size), from members who voted yes or no (db voteSplit). */
export const partySplitSentence = (split: {
  dem: { yes: number; no: number };
  rep: { yes: number; no: number };
}): string => {
  const side = (c: { yes: number; no: number }) => (c.yes > c.no ? "yes" : c.yes < c.no ? "no" : null);
  const d = side(split.dem);
  const r = side(split.rep);
  const tally = (c: { yes: number; no: number }) => `${c.yes.toLocaleString()} yes and ${c.no.toLocaleString()} no`;
  const tallies = `Democrats ${tally(split.dem)}, Republicans ${tally(split.rep)}`;
  const among = "Of members who voted yes or no";
  if (d && r && d === r) return `${among}, most of both parties voted ${d}: ${tallies}.`;
  if (d && r) return `A party-line vote. ${among}, most Democrats voted ${d} and most Republicans voted ${r}: ${tallies}.`;
  const tied = d === null && r === null ? "Both parties" : d === null ? "Democrats" : "Republicans";
  return `${among}: ${tallies}. ${tied} split evenly.`;
};

export const partyLetter = (party: string | null): string =>
  party ? party[0] : "?";

/** Truncate with an ellipsis, preferring a nearby word boundary. */
export const clip = (text: string, max: number): string => {
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return (space > max * 0.6 ? cut.slice(0, space) : cut).replace(/[,;:.\s]+$/, "") + "…";
};

/** The four-digit year a session id starts with: "2025" -> 2025. */
export const sessionYear = (sessionId: string): string => sessionId.slice(0, 4);

/** Bill titles all open "Relating to: ..."; strip it for compact rows. */
export const shortTitle = (title: string | null): string =>
  (title ?? "")
    // Source titles vary in whitespace after the prefix.
    .replace(/^\s*relating to:\s*/i, "")
    .replace(/^./, (c) => c.toUpperCase());

/** Join source hard wraps; blank lines or terminal punctuation end paragraphs. */
export const lrbParagraphs = (analysis: string): string[] => {
  const paras: string[] = [];
  let current: string[] = [];
  for (const raw of analysis.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) {
      if (current.length) paras.push(current.join(" "));
      current = [];
      continue;
    }
    current.push(line);
    if (/[.:;?!]["')\]]?$/.test(line)) {
      paras.push(current.join(" "));
      current = [];
    }
  }
  if (current.length) paras.push(current.join(" "));
  return paras.filter(Boolean);
};

/** Committee page slug: the tail of the scraped committee id. */
export const committeeSlug = (id: string): string => id.split("/").pop()!;

export const roleAbbr = (chamber: string | null): string =>
  chamber === "upper" ? "SD" : "AD";

export const chamberName = (chamber: string | null): string =>
  chamber === "lower" ? "Assembly" : chamber === "upper" ? "Senate" : "Legislature";

/** A committee's full name, the way the Legislature writes it: "Assembly
 * Committee on Education". Joint committees, and bodies that name
 * themselves (a task force, a council, a board), keep their own name. */
export const committeeTitle = (name: string, chamber: string | null): string => {
  if (!chamber) return name;
  if (/\b(task force|council|commission|board|committee)\b/i.test(name) && !/^committee on /i.test(name)) return name;
  const house = chamberName(chamber);
  return /^committee on /i.test(name) ? `${house} ${name}` : `${house} Committee on ${name}`;
};

/** A committee's house, where a null chamber means a joint committee. */
export const committeeChamber = (chamber: string | null): string =>
  chamber ? chamberName(chamber) : "Joint";

/** Consistent hearing names for the calendar JSON and hearing list. */
export const hearingDisplayName = (h: {
  committee_name: string | null;
  committee_chamber: string | null;
  title: string | null;
}): string =>
  h.committee_name
    ? committeeTitle(h.committee_name, h.committee_chamber)
    : (h.title ?? "Committee hearing");

export const billSlug = (identifier: string): string =>
  identifier.replace(/\s+/g, "").toLowerCase();

/** Committed slugs survive name changes; unmapped people keep the legacy ID fallback. */
export const personSlug = (personId: string): string =>
  PERSON_SLUGS[personId] ?? personId.replace(/^legacy\//, "legacy-").split("/").pop()!;

/** '13:01' (already America/Chicago) -> '1:01 PM' */
export const fmtTime = (t: string | null): string => {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  const h12 = h % 12 || 12;
  return `${h12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"} CT`;
};

/** Whole dollars, sign first: "-$1,234" (refunds can make a total negative). */
export const fmtMoney = (v: number): string => {
  const r = Math.round(v);
  return (r < 0 ? "-$" : "$") + Math.abs(r).toLocaleString("en-US");
};

/** Money in a sentence: whole dollars, rounded once it's large
 * ("$4.8 million"); exact figures go in the table beneath (docs/brand.md,
 * "Numbers"). */
export const fmtMoneyShort = (v: number): string => {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1).replace(/\.0$/, "")} billion`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1).replace(/\.0$/, "")} million`;
  return fmtMoney(v);
};

/** Dollars to the cent, for figures reported to the cent. */
export const fmtCents = (v: number): string =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

export { subjectDisplay, subjectSlug } from "./subjects.ts";

export const monthYear = (iso: string): string =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

export const fmtDate = (iso: string | null): string => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
};

// statutory compensation (s. 20.923); salary is identical for every member
export const COMPENSATION = {
  salary: 60924,
  assembly: { overnight: 171, day: 85.5 },
  senate: { overnight: 140, note: "half rate for Dane County members" },
};
