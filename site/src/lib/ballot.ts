/** What the Elections Commission's ballot-access report says about a
 * sitting member's seat. The report is the only source: a row with no
 * status posted yet is "pending", never read as a retirement or as a
 * candidacy. Client scripts import this too, so it reads no database. */
import { partyWord } from "./format.ts";
import { esc, safeHref } from "./html.ts";

export const ELECTION_CYCLE = 2026;

/** The Commission's office name for a legislative seat, as its records spell it. */
export const seatOffice = (chamber: string | null, district: number | null): string =>
  `${chamber === "upper" ? "STATE SENATOR" : "REPRESENTATIVE TO THE ASSEMBLY"} DISTRICT ${district}`;

export type BallotStatus =
  | { kind: "on-ballot" | "not-running" | "pending" | "future"; year: number }
  | { kind: "none" };

export const ballotStatus = (
  election: { cycle_year: number; on_ballot: number | null } | null | undefined,
  cycle: number = ELECTION_CYCLE,
): BallotStatus => {
  if (!election) return { kind: "none" };
  const year = election.cycle_year;
  if (year !== cycle) return { kind: "future", year };
  const kind =
    election.on_ballot === 1 ? "on-ballot" : election.on_ballot === 0 ? "not-running" : "pending";
  return { kind, year };
};

/** Why a party's nominee isn't settled, in a sentence, from the
 * certified primary (importer/wec_primary.py names the reason). */
export const writeInSentence = (pending: { party: string; reason: string }[]): string =>
  pending
    .map(({ party, reason }) =>
      /tied/i.test(reason)
        ? `The ${party} primary ended in a tie, so its nominee isn't settled yet.`
        : /could exceed/i.test(reason)
          ? `In the ${party} primary, write-in votes could outnumber the leader's, so its nominee isn't settled yet.`
          : /qualified/i.test(reason)
            ? `The ${party} primary had no printed candidate, and a write-in candidate may have qualified.`
            : `The ${party} primary's nominee isn't settled yet.`,
    )
    .join(" ");

// ---- words for races and results, shared by pages and client scripts ----

/** The five statewide constitutional offices, in ballot order, as the
 * Commission keys them and as we say them. */
export const STATEWIDE_OFFICES: [string, string][] = [
  ["GOVERNOR", "Governor"],
  ["LIEUTENANT GOVERNOR", "Lieutenant governor"],
  ["ATTORNEY GENERAL", "Attorney general"],
  ["SECRETARY OF STATE", "Secretary of state"],
  ["STATE TREASURER", "State treasurer"],
];

export const article = (word: string): string => (/^[aeiou]/i.test(word) ? "an" : "a");

/** "Dana Whitfield, a Democrat" */
export const withParty = (name: string, party: string | null): string =>
  party ? `${name}, ${article(partyWord(party))} ${partyWord(party)}` : name;

/** A name as a sentence's subject: "Dana Whitfield, a Democrat," */
export const subject = (name: string, party: string | null): string =>
  party ? `${withParty(name, party)},` : name;

/** Join names; once a name carries ", a Republican" the joins need a comma
 * before "and", and semicolons from three on. */
export const nameList = (xs: string[]): string => {
  if (xs.length < 2) return xs.join("");
  const commas = xs.some((x) => x.includes(","));
  // only the first name's own commas call for one before "and"
  if (xs.length === 2) return `${xs[0]}${xs[0].includes(",") ? "," : ""} and ${xs[1]}`;
  const sep = commas ? "; " : ", ";
  return `${xs.slice(0, -1).join(sep)}${sep}and ${xs.at(-1)}`;
};

/** "51.2%" of the votes cast, or "" without a total. */
export const pctOf = (votes: number, total: number): string =>
  total ? `${((votes / total) * 100).toFixed(1)}%` : "";

// a governor's ticket ("Evers / Rodriguez") reads as one subject
const ticket = (name: string, party: string | null): string | null =>
  name.includes(" / ")
    ? `the ${party ? `${party} ` : ""}ticket of ${nameList(name.split(" / ").map((n) => n.trim()))}`
    : null;

/** One sentence on who won a certified contest, honest about ties,
 * unopposed races and missing totals. */
export const resultSentence = (
  candidates: { candidate: string; party: string | null; votes: number }[],
  total: number,
): string => {
  const [first] = candidates;
  if (!first) return "";
  const cast = total ? ` of ${total.toLocaleString()} votes cast` : "";
  const firstTicket = ticket(first.candidate, first.party);
  const lead = firstTicket ? `${firstTicket[0].toUpperCase()}${firstTicket.slice(1)}` : subject(first.candidate, first.party);
  if (candidates.length === 1) {
    return `${lead} ran unopposed and got ${first.votes.toLocaleString()}${cast || " votes"}.`;
  }
  const tied = candidates.filter((c) => c.votes === first.votes);
  if (tied.length > 1) {
    const names = tied.map((c) => ticket(c.candidate, c.party) ?? withParty(c.candidate, c.party));
    const tail = names.at(-1)!.includes(",") ? "," : "";
    const sentence = `${nameList(names)}${tail} tied with ${first.votes.toLocaleString()} votes each.`;
    return `${sentence[0].toUpperCase()}${sentence.slice(1)}`;
  }
  return total
    ? `${lead} won with ${pctOf(first.votes, total)}${cast}.`
    : `${lead} won with ${first.votes.toLocaleString()} votes.`;
};

export interface RaceFacts {
  /** The member who holds the seat now. */
  holder: { name: string; party: string | null; href?: string | null } | null;
  status: "on-ballot" | "not-running" | "pending";
  /** Everyone else on (or approved for) the ballot. */
  others: { name: string; party: string | null; href?: string | null; challenged?: boolean }[];
  phase: "general" | "primary";
  /** A party primary for this seat whose nominee isn't settled yet: the
   * incumbent may not be unopposed after all. */
  unsettled?: boolean;
}

const personHtml = (p: { name: string; href?: string | null }): string => {
  const href = safeHref(p.href);
  return href ? `<a href="${esc(href)}" class="underline">${esc(p.name)}</a>` : esc(p.name);
};

/** A legislative race in a sentence or two, as HTML (names escaped, linked
 * when they have a page). One wording for the race lists, race pages and
 * the reader's own ballot. */
export const raceSentenceHtml = (r: RaceFacts): string => {
  const others = nameList(
    r.others.map((o) =>
      (o.party ? `${personHtml(o)}, ${article(partyWord(o.party))} ${esc(partyWord(o.party))}` : personHtml(o)) +
      (o.challenged ? " (ballot access challenged)" : ""),
    ),
  );
  const verb = r.others.length === 1 ? "is" : "are";
  // "Jordan Pike, a Democrat, is": the party phrase closes with a comma
  const close = r.others.at(-1)?.party ? "," : "";
  const h = r.holder;
  const holderHtml = h ? `${personHtml(h)}, the ${h.party ? `${esc(h.party)} ` : ""}incumbent,` : "";
  if (r.status === "on-ballot" && h) {
    if (r.others.length) return `${holderHtml} faces ${others}.`;
    if (r.unsettled) return `${holderHtml} is on the ballot. No other nominee for this seat is settled yet.`;
    return r.phase === "general"
      ? `${holderHtml} is running unopposed.`
      : `${holderHtml} is the only approved candidate so far.`;
  }
  const field = r.others.length
    ? ` ${others}${close} ${verb} ${r.phase === "general" ? "on the ballot" : "approved for the ballot"}.`
    : r.status === "pending"
      ? " No other candidates are listed yet."
      : r.phase === "general"
        ? " No candidate is on the ballot for this seat."
        : " No candidates are approved for the ballot yet.";
  if (r.status === "not-running" && h) return `${holderHtml} isn't on the ballot.${field}`;
  if (r.status === "pending" && h) {
    return `The Elections Commission hasn't posted whether ${personHtml(h)} is running.${field}`;
  }
  return field.trim();
};
