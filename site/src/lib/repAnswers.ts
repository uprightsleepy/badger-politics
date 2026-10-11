/** A sitting lawmaker's record as plain questions and one-sentence answers.
 *
 * Shared by the My reps cards (built in the browser) and each lawmaker's
 * own page (built at build time), so the two never word the same fact two
 * ways. Pure and browser-safe: it reads only the summary it is handed.
 * Every value that reaches the HTML goes through esc(). */
import { ballotStatus, nameList, withParty, writeInSentence } from "./ballot.ts";
import { clip, fmtDate, partyPlural } from "./format.ts";
import { esc } from "./html.ts";
import type { RepSummary, Typical } from "./wire.ts";

export interface AnswerContext {
  house: "assembly" | "senate";
  district: number;
  typical: { notVoting: Typical | null; loyalty: Typical | null } | null | undefined;
  phase: "general" | "primary" | undefined;
  /** ISO date of this cycle's general election, when known. */
  general: string;
  /** On My reps the reader is looking at their own lawmakers. */
  mine: boolean;
}

export interface Answer {
  id: "voting" | "party" | "bills" | "committees" | "ballot" | "recent";
  q: string;
  html: string;
}

const fig = (n: number | string) => `<span class="figure">${esc(String(n))}</span>`;
const link = (href: string, text: string) => `<a href="${esc(href)}" class="underline">${esc(text)}</a>`;
const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
const round = (n: number) => Math.round(n);
const fine = (text: string) => `<p class="text-fine text-granite">${text}</p>`;

/** Sentences spell the month out: "November 3, 2026". */
export const longDate = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    month: "long", day: "numeric", year: "numeric", timeZone: "UTC",
  });
};

/** "Avery Lund, a Republican, and Jordan Pike, a Democrat" */
const people = (list: { name: string; party: string | null }[]) =>
  nameList(list.map((p) => esc(withParty(p.name, p.party))));

/** One value against the middle half of the chamber, with the value
 * itself under the marker. No end labels: the band and the note under it
 * give the comparison. The sentence beside it states the same facts, so
 * the bar is hidden from assistive tech. */
const rangeBar = (o: { value: number; min: number; max: number; typical: Typical }) => {
  const span = Math.max(o.max - o.min, 1);
  const pos = (n: number) => Math.min(100, Math.max(0, ((n - o.min) / span) * 100));
  // a band too narrow to see still shows, inside the track at either end
  const width = Math.max(pos(o.typical.high) - pos(o.typical.low), 2);
  const lo = Math.min(pos(o.typical.low), 100 - width);
  const at = pos(o.value);
  // never "100%" for someone who missed one; never past the track's ends
  const label = o.value < 100 ? `${Math.min(99, round(o.value))}%` : "100%";
  const shift = at > 88 ? "-100%" : at < 12 ? "0%" : "-50%";
  return (
    '<div class="range mt-1" aria-hidden="true">' +
    '<div class="relative mx-2.5 h-2.5 rounded-full bg-fog">' +
    `<span class="absolute inset-y-0 rounded-full bg-lake-tint" style="left:${lo.toFixed(1)}%;width:${width.toFixed(1)}%"></span>` +
    `<span class="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-spruce" style="left:${at.toFixed(1)}%"></span>` +
    '</div>' +
    '<div class="relative mx-2.5 mt-2 h-5">' +
    `<span class="absolute whitespace-nowrap text-small font-bold text-spruce" style="left:${at.toFixed(1)}%;transform:translateX(${shift})">${esc(label)}</span>` +
    '</div>' +
    '</div>'
  );
};

const ROLE_RANK = (role: string) =>
  /^chair/i.test(role) ? 0 : /^co-chair/i.test(role) ? 1 : /^vice/i.test(role) ? 2 : 3;
const ROLE_LABEL = (role: string) =>
  /^chair/i.test(role) ? "Chair" : /^co-chair/i.test(role) ? "Co-chair" : /^vice/i.test(role) ? "Vice-chair" : "Member";

export function answers(full: RepSummary, ctx: AnswerContext): Answer[] {
  const out: Answer[] = [];
  const members = ctx.house === "assembly" ? "representatives" : "senators";
  const t = ctx.typical;

  // 1. how often they vote: yes or no, out of every roll call held while
  // they served, against the rest of their chamber
  const v = full.voted;
  if (v && v.total > 0) {
    const skipped = v.total - v.cast;
    let html = skipped === 0
      ? `<p>Voted on all ${fig(v.total.toLocaleString())} roll call votes this session.</p>`
      : `<p>Voted on ${fig(v.cast.toLocaleString())} of ${fig(v.total.toLocaleString())} roll call votes this session. Didn't vote on ${fig(skipped.toLocaleString())}.</p>`;
    const nv = t?.notVoting;
    if (nv) {
      // the bar reads the way the sentence does: the share they voted on,
      // more to the right, the share itself under the marker. The track
      // starts at the chamber's lowest share (at least 5 points down).
      const share = (v.cast / v.total) * 100;
      const typical = { ...nv, low: 100 - nv.high, high: 100 - nv.low, max: 100 };
      const pct = (n: number) => (n < 100 && round(n) === 100 ? "over 99%" : `${round(n)}%`);
      const words = round(nv.high) === 0 && nv.high < 0.5
        ? `The middle half of ${members} voted on every one, or nearly.`
        : `The middle half of ${members} voted on ${pct(typical.low)} to ${pct(typical.high)} of them.`;
      const floor = Math.min(95, Math.floor(Math.min(100 - nv.max, share)));
      html += rangeBar({ value: share, min: floor, max: 100, typical }) +
        fine(`${esc(words)} Not voting counts being away and choosing not to vote alike.`);
    }
    out.push({ id: "voting", q: "How often do they vote?", html });
  } else {
    out.push({ id: "voting", q: "How often do they vote?", html: "<p>No roll call votes are recorded for them yet this session.</p>" });
  }

  // 2. party agreement, Democrats and Republicans only
  if (full.party === "Democratic" || full.party === "Republican") {
    const l = full.loyalty;
    let html: string;
    if (l) {
      const pct = round(l.pct);
      html = `<p>Voted with most ${esc(partyPlural(full.party))} on ${fig(`${pct}%`)} of ${fig(l.n.toLocaleString())} votes in the ${esc(l.label)}.</p>`;
      const lt = t?.loyalty;
      if (lt && lt.session === l.session) {
        html += rangeBar({ value: l.pct, min: 50, max: 100, typical: lt }) +
          fine(esc(`The middle half of ${members} voted with their party ${round(lt.low)}% to ${round(lt.high)}% of the time.`));
      }
    } else {
      html = "<p>Not enough recorded votes yet this session to measure.</p>";
    }
    out.push({ id: "party", q: "How often do they vote with their party?", html });
  }

  // 3. bills
  const au = full.authored;
  const bills =
    (au.total > 0
      ? `Led ${fig(au.total)} ${plural(au.total, "bill", "bills")} this session.` +
        (au.enacted === 0 ? " None became law." : ` ${fig(au.enacted)} became law.`) +
        (au.vetoed ? ` ${fig(au.vetoed)} ${plural(au.vetoed, "was", "were")} vetoed.` : "") +
        (au.noHearing ? ` ${fig(au.noHearing)} never got a hearing.` : "")
      : "They haven't led a bill this session.") +
    (au.signedOn ? ` Signed on in support of ${fig(au.signedOn)} more.` : "");
  out.push({
    id: "bills",
    q: "What have they tried to pass?",
    html: `<p>${bills}${ctx.mine ? ` ${link(`/legislators/${full.slug}/#bills-led`, "See their bills")}` : ""}</p>`,
  });

  // 4. committees, leaders first
  const cs = (full.committees ?? []).slice().sort((x, y) => ROLE_RANK(x.role) - ROLE_RANK(y.role));
  if (cs.length) {
    const byRole = new Map<string, string[]>();
    for (const c of cs) {
      const role = ROLE_LABEL(c.role);
      byRole.set(role, [...(byRole.get(role) ?? []), link(`/committees/${c.slug}/`, c.name)]);
    }
    out.push({
      id: "committees",
      q: "Which committees are they on?",
      html: '<ul class="flex flex-col gap-1">' +
        [...byRole.entries()].map(([role, list]) => `<li><span class="font-bold">${role}:</span> ${list.join(", ")}</li>`).join("") +
        '</ul>',
    });
  }

  // 5. the ballot
  const status = ballotStatus(full.election);
  const opponents = full.opponents ?? [];
  const writeIns = full.writeInPending ?? [];
  const when = ctx.general ? longDate(ctx.general) : "";
  const seat = status.kind !== "none" ? `/elections/${status.year}/${ctx.house}-${ctx.district}/` : "";
  const raceLink = status.kind !== "none" && status.kind !== "future" ? ` ${link(seat, "See the race")}` : "";
  // a nominee the certified results don't settle yet: say why
  const reasons = full.writeInReasons?.length
    ? full.writeInReasons
    : writeIns.map((party) => ({ party, reason: "" }));
  const writeInLine = reasons.length ? ` ${esc(writeInSentence(reasons))}` : "";
  let ballot = "";
  if (status.kind === "on-ballot") {
    ballot = ctx.phase === "general"
      ? opponents.length
        ? `Yes. ${when ? `On ${esc(when)}, they` : "They"} face ${people(opponents)}.`
        : writeIns.length
          ? `Yes. No other nominee for this seat is settled yet${when ? ` for ${esc(when)}` : ""}.`
          : `Yes. They're running unopposed${when ? ` on ${esc(when)}` : ""}.`
      : `Yes, they're on the ${status.year} ballot.` + (opponents.length ? ` Others approved for this seat: ${people(opponents)}.` : "");
    ballot += writeInLine;
  } else if (status.kind === "not-running") {
    // not on the November ballot: retired, lost a primary, or not
    // approved; the report doesn't say which, so neither do we
    ballot = `No. They're not on the November ${status.year} ballot.` +
      (opponents.length ? ` On the ballot for this seat: ${people(opponents)}.` : "") + writeInLine;
  } else if (status.kind === "pending") {
    ballot = `The Elections Commission hasn't posted yet whether they're running in ${status.year}.`;
  } else if (status.kind === "future") {
    ballot = `Not this year. This seat is next on the ballot in ${status.year}.`;
  }
  if (ballot) {
    out.push({
      id: "ballot",
      q: ctx.mine ? "Are they on your ballot?" : "Are they on the ballot this year?",
      html: `<p>${ballot}${raceLink}</p>` +
        (status.kind !== "future"
          ? fine("From the Elections Commission's ballot report. Check MyVote Wisconsin for your own ballot.")
          : ""),
    });
  }

  // 6. the latest vote, then the few before it
  const votes = full.recentVotes ?? [];
  const voteLine = (vote: RepSummary["recentVotes"][number], long: boolean) => {
    const how = vote.option === "yes" ? "Voted yes" : vote.option === "no" ? "Voted no" : "Didn't vote";
    // the official title, as written, after its "Relating to:"
    const about = (vote.title ?? "").replace(/^\s*relating to:\s*/i, "").replace(/\.\s*$/, "");
    const subject = about ? `, relating to ${esc(clip(about, long ? 90 : 60))}` : "";
    return `${how} on ${link(`/bills/${vote.session}/${vote.slug}/`, vote.identifier)}${subject}. ${esc(fmtDate(vote.date))}. ${link(`/votes/${vote.event}/`, long ? "See the vote" : "Vote")}` +
      (vote.motion ? `<span class="block text-fine text-granite">Official motion: “${esc(vote.motion)}”</span>` : "");
  };
  if (votes.length) {
    let html = `<p>${voteLine(votes[0], true)}</p>`;
    if (votes.length > 1 && ctx.mine) {
      html +=
        '<details class="group"><summary class="inline-flex min-h-11 cursor-pointer list-none items-center font-display font-bold text-lake underline underline-offset-4 [&::-webkit-details-marker]:hidden">' +
        `<span class="group-open:hidden">See ${votes.length - 1} earlier ${plural(votes.length - 1, "vote", "votes")}</span><span class="hidden group-open:inline">Hide earlier votes</span></summary>` +
        '<ul class="flex flex-col">' +
        votes.slice(1).map((x) => `<li class="border-t border-rule py-2 text-small">${voteLine(x, false)}</li>`).join("") +
        '</ul></details>';
    }
    out.push({ id: "recent", q: "How did they vote most recently?", html });
  }
  return out;
}
