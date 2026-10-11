/** One sitting lawmaker's quick-glance record, and each chamber's
 * yardsticks to read it against. Build time only (reads the database).
 *
 * The same summary feeds /data/rep-summaries.json (the My reps cards) and
 * the "at a glance" answers on each lawmaker's own page, so both say the
 * same thing in the same words. */
import {
  sittingPeople, personVotes, committeesFor, writeInPending,
  allSessions, currentSessions, bienniumOf, type Person,
} from "./db.ts";
import { once } from "./connection.ts";
import { legislatorProfile } from "./legislator.ts";
import { seatOffice } from "./ballot.ts";
import { billSlug, committeeSlug, personSlug, sessionPlainName } from "./format.ts";
import type { RepSummary, Typical } from "./wire.ts";

// party agreement needs this many votes before it is a fair number
const LOYALTY_MIN = 20;

/** The 25th to 75th percentile, linearly interpolated. */
export const middleHalf = (values: number[]): Typical | null => {
  if (values.length < 4) return null;
  const v = [...values].sort((a, b) => a - b);
  const at = (q: number) => {
    const i = (v.length - 1) * q;
    const lo = Math.floor(i);
    return v[lo] + (v[Math.min(lo + 1, v.length - 1)] - v[lo]) * (i - lo);
  };
  return { low: at(0.25), high: at(0.75), max: v[v.length - 1], members: v.length };
};

const sessionNames = once(() => new Map(allSessions().map((s) => [s.id, s.name ?? s.id])));
const bienniumStart = once(() => {
  const sessions = currentSessions();
  return sessions.length ? `${bienniumOf(sessions[0].id)}-01-01` : null;
});

const byId = new Map<string, RepSummary>();
/** Keyed by person id: profile pages and the endpoint hold different
 * row objects for the same member. */
export const repSummary = (p: Person): RepSummary => {
  const hit = byId.get(p.id);
  if (hit) return hit;
  const summary = build(p);
  byId.set(p.id, summary);
  return summary;
};

const build = (p: Person): RepSummary => {
  const profile = legislatorProfile(p);
  // this biennium only; the career totals are on the profile page
  const { attendance, authorship: au } = profile.biennium;
  // votes they cast (yes or no) out of every roll call held while they
  // served: "didn't vote" covers absences and recorded non-votes alike
  const start = bienniumStart();
  const served = start
    ? profile.heatDays.filter((d) => d.served !== false && d.date >= start)
    : [];
  const voted = {
    cast: served.reduce((n, d) => n + d.cast, 0),
    total: served.reduce((n, d) => n + d.total, 0),
  };
  // newest regular session with enough votes; special sessions are short
  // and their ids sort out of order
  const agreement = profile.agreement
    .filter((a) => /^\d{4}$/.test(a.session) && a.n >= LOYALTY_MIN)
    .sort((a, b) => b.session.localeCompare(a.session))[0];
  const election = profile.election;
  return {
    name: p.name,
    party: p.party,
    slug: personSlug(p.id),
    role: p.current_role,
    contact: p.email ? { email: p.email, phone: p.office_phone } : null,
    committees: committeesFor(p.id).map((c) => ({
      name: c.name,
      role: c.role,
      slug: committeeSlug(c.id),
    })),
    attendance,
    voted,
    authored: {
      total: au.led.length,
      signedOn: au.coauthored.length + au.cosponsored.length,
      enacted: au.enacted,
      vetoed: au.vetoed,
      noHearing: au.noHearing,
    },
    election: election ? { cycle_year: election.cycle_year, on_ballot: election.on_ballot } : null,
    // only filings the Elections Commission approved, as the race pages list
    opponents: (election?.opponents ?? [])
      .filter((o) => o.ballot_status === "Approve")
      .map((o) => ({ name: o.name, party: o.party ?? null })),
    writeInPending:
      election?.cycle_year === 2026
        ? writeInPending(seatOffice(p.chamber, p.district)).map((w) => w.party)
        : [],
    writeInReasons:
      election?.cycle_year === 2026
        ? writeInPending(seatOffice(p.chamber, p.district)).map((w) => ({ party: w.party, reason: w.reason }))
        : [],
    loyalty: agreement
      ? {
          pct: agreement.pct,
          n: agreement.n,
          session: agreement.session,
          label: sessionPlainName(agreement.session, sessionNames().get(agreement.session) ?? agreement.session),
        }
      : null,
    // public JSON: never LegiScan's rows (CLAUDE.md)
    recentVotes: personVotes(p.id, 5, 0, { noLegiscan: true }).map((v) => ({
      date: v.date,
      option: v.option,
      // the same bill can appear twice in a day (suspension, then passage);
      // the motion is what tells the two rows apart
      motion: v.motion,
      identifier: v.identifier,
      slug: billSlug(v.identifier),
      title: v.title,
      session: v.session_id,
      event: v.vote_event_id,
    })),
  };
};

type House = "assembly" | "senate";
export type ChamberTypical = Record<House, { notVoting: Typical | null; loyalty: Typical | null }>;

/** Each chamber's middle half of sitting members: how often they don't
 * vote (a rate, so members seated mid-session compare fairly) and how
 * often they vote with their party (within one session, never mixed). */
export const chamberTypical = once((): ChamberTypical => {
  const notVoting: Record<House, number[]> = { assembly: [], senate: [] };
  const loyalty: Record<House, { pct: number; session: string }[]> = { assembly: [], senate: [] };
  for (const p of sittingPeople()) {
    const s = repSummary(p);
    const house: House = p.chamber === "upper" ? "senate" : "assembly";
    if (s.voted.total > 0) notVoting[house].push(((s.voted.total - s.voted.cast) / s.voted.total) * 100);
    if (s.loyalty) loyalty[house].push(s.loyalty);
  }
  const sameSession = (rows: { pct: number; session: string }[]): Typical | null => {
    const counts = new Map<string, number>();
    for (const r of rows) counts.set(r.session, (counts.get(r.session) ?? 0) + 1);
    const session = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    const t = middleHalf(rows.filter((r) => r.session === session).map((r) => r.pct));
    return t && session ? { ...t, session } : null;
  };
  return {
    assembly: { notVoting: middleHalf(notVoting.assembly), loyalty: sameSession(loyalty.assembly) },
    senate: { notVoting: middleHalf(notVoting.senate), loyalty: sameSession(loyalty.senate) },
  };
});
