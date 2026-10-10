/** Per-sitting-legislator quick-glance data for the client-side my-reps
 * cards: recent roll-call votes, this-biennium attendance and authorship,
 * committees, and ballot status. Device-side lookup only: the page picks
 * the two entries matching the locally saved districts.
 *
 * It also carries each chamber's yardsticks (the middle half of sitting
 * members on how often they vote and how often they vote with their
 * party), so a single member's number is never shown bare. */
import type { APIRoute } from "astro";
import {
  sittingPeople, personVotes, committeesFor, ballotPhase, writeInPending,
  allSessions, currentSessions, bienniumOf,
} from "../../lib/db";
import { legislatorProfile } from "../../lib/legislator";
import { seatOffice } from "../../lib/ballot";
import { billSlug, committeeSlug, personSlug, sessionPlainName } from "../../lib/format";
import type { RepSummary, Typical } from "../../lib/wire";

/** The 25th to 75th percentile, linearly interpolated. */
const middleHalf = (values: number[]): Typical | null => {
  if (values.length < 4) return null;
  const v = [...values].sort((a, b) => a - b);
  const at = (q: number) => {
    const i = (v.length - 1) * q;
    const lo = Math.floor(i);
    return v[lo] + (v[Math.min(lo + 1, v.length - 1)] - v[lo]) * (i - lo);
  };
  return { low: at(0.25), high: at(0.75), max: v[v.length - 1], members: v.length };
};

// party agreement needs this many votes before it is a fair number
const LOYALTY_MIN = 20;

export const GET: APIRoute = () => {
  const assembly: Record<string, RepSummary> = {};
  const senate: Record<string, RepSummary> = {};
  type House = "assembly" | "senate";
  const notVoting: Record<House, number[]> = { assembly: [], senate: [] };
  const loyalty: Record<House, { pct: number; session: string }[]> = { assembly: [], senate: [] };
  const sessionNames = new Map(allSessions().map((s) => [s.id, s.name ?? s.id]));
  const sessions = currentSessions();
  const bienniumStart = sessions.length ? `${bienniumOf(sessions[0].id)}-01-01` : null;
  const phase = ballotPhase();

  for (const p of sittingPeople()) {
    const profile = legislatorProfile(p);
    // this biennium only; the career totals are on the profile page
    const { attendance, authorship: au } = profile.biennium;
    // votes they cast (yes or no) out of every roll call held while they
    // served: "didn't vote" covers absences and recorded non-votes alike
    const served = bienniumStart
      ? profile.heatDays.filter((d) => d.served !== false && d.date >= bienniumStart)
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
    const entry: RepSummary = {
      name: p.name,
      party: p.party,
      slug: personSlug(p.id),
      role: p.current_role,
      contact: p.email
        ? { email: p.email, phone: p.office_phone }
        : null,
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
      election: election
        ? { cycle_year: election.cycle_year, on_ballot: election.on_ballot }
        : null,
      // only filings the Elections Commission approved, as the race pages list
      opponents: (election?.opponents ?? [])
        .filter((o) => o.ballot_status === "Approve")
        .map((o) => ({ name: o.name, party: o.party ?? null })),
      writeInPending:
        election?.cycle_year === 2026
          ? writeInPending(seatOffice(p.chamber, p.district)).map((w) => w.party)
          : [],
      loyalty: agreement
        ? {
            pct: agreement.pct,
            n: agreement.n,
            session: agreement.session,
            label: sessionPlainName(agreement.session, sessionNames.get(agreement.session) ?? agreement.session),
          }
        : null,
      recentVotes: personVotes(p.id, 5).map((v) => ({
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
    if (p.chamber === "lower" && p.district != null) assembly[p.district] = entry;
    if (p.chamber === "upper" && p.district != null) senate[p.district] = entry;
    const house: House = p.chamber === "upper" ? "senate" : "assembly";
    // a rate, so members seated mid-session compare fairly
    if (voted.total > 0) notVoting[house].push(((voted.total - voted.cast) / voted.total) * 100);
    if (entry.loyalty) loyalty[house].push(entry.loyalty);
  }

  // party agreement compares only within the session most members are
  // measured on, so a yardstick never mixes sessions
  const sameSession = (rows: { pct: number; session: string }[]): Typical | null => {
    const counts = new Map<string, number>();
    for (const r of rows) counts.set(r.session, (counts.get(r.session) ?? 0) + 1);
    const session = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    const t = middleHalf(rows.filter((r) => r.session === session).map((r) => r.pct));
    return t && session ? { ...t, session } : null;
  };
  const typical = {
    assembly: { notVoting: middleHalf(notVoting.assembly), loyalty: sameSession(loyalty.assembly) },
    senate: { notVoting: middleHalf(notVoting.senate), loyalty: sameSession(loyalty.senate) },
  };
  return new Response(JSON.stringify({ assembly, senate, phase, typical }), {
    headers: { "Content-Type": "application/json" },
  });
};
