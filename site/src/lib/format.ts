import PERSON_SLUGS from "../data/person-slugs.json" with { type: "json" };
import { esc } from "./html.ts";

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

export const STATUS_SHORT: Record<string, string> = {
  introduced: "Introduced",
  in_committee: "In committee",
  passed_chamber: "Passed 1 house",
  passed: "Passed both",
  adopted: "Adopted",
  enacted: "Law",
  vetoed: "Vetoed",
  failed_sjr1: "Died",
};

// Status is told by its words, never by color: every status shares one
// neutral chip (docs/brand.md, "No status colors").
const STATUS_CHIP = "bg-fog text-spruce";
export const STATUS_STYLES: Record<string, string> = Object.fromEntries(
  Object.keys(STATUS_LABELS).map((k) => [k, STATUS_CHIP]),
);

// Party is a word, not a color: one neutral style for every party.
export const partyStyle = (_party: string | null): string =>
  "bg-white text-spruce ring-1 ring-inset ring-edge";

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

export const partyLetter = (party: string | null): string =>
  party ? party[0] : "?";

/** Party markup shared by Astro and browser cards. Use decorative when
 * adjacent text already names the party, avoiding duplicate announcements. */
export const partyChipHtml = (
  party: string | null,
  { dims = "h-5 w-5 text-xs", decorative = false }: { dims?: string; decorative?: boolean } = {},
): string => {
  const a11y = decorative
    ? ' aria-hidden="true"'
    : ` role="img" aria-label="${esc(party ?? "party unknown")}"`;
  return (
    `<span class="inline-flex ${dims} shrink-0 items-center justify-center rounded-full font-bold ${partyStyle(party)}"${a11y}>` +
    `<span aria-hidden="true">${esc(partyLetter(party))}</span></span>`
  );
};

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

export const fmtMoney = (v: number): string =>
  "$" + Math.round(v).toLocaleString("en-US");

/** Dollars to the cent, for figures reported to the cent. */
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
