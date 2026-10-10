/** Per-sitting-legislator quick-glance data for the client-side my-reps
 * cards: recent roll-call votes, this-biennium attendance and authorship,
 * committees, and ballot status. Device-side lookup only: the page picks
 * the two entries matching the locally saved districts. */
import type { APIRoute } from "astro";
import { sittingPeople, personVotes, committeesFor, ballotPhase } from "../../lib/db";
import { legislatorProfile } from "../../lib/legislator";
import { billSlug, committeeSlug, personSlug } from "../../lib/format";
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

export const GET: APIRoute = () => {
  const assembly: Record<string, RepSummary> = {};
  const senate: Record<string, RepSummary> = {};
  const missed: Record<"assembly" | "senate", number[]> = { assembly: [], senate: [] };
  const loyalty: Record<"assembly" | "senate", { pct: number; session: string }[]> = { assembly: [], senate: [] };

  for (const p of sittingPeople()) {
    const profile = legislatorProfile(p);
    // this biennium only; the career totals are on the profile page
    const { attendance, authorship: au } = profile.biennium;
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
      authored: {
        total: au.led.length,
        signedOn: au.coauthored.length + au.cosponsored.length,
        enacted: au.enacted,
        vetoed: au.vetoed,
        noHearing: au.noHearing,
      },
      election: profile.election
        ? { cycle_year: profile.election.cycle_year, on_ballot: profile.election.on_ballot }
        : null,
      opponents: profile.opponents.map((o) => ({ name: o.name, party: o.party ?? null })),
      loyalty: profile.loyalty
        ? { pct: profile.loyalty.pct, n: profile.loyalty.n, session: profile.loyalty.session }
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
    const house = p.chamber === "upper" ? "senate" : "assembly";
    if (attendance.total > 0) missed[house].push(attendance.missed);
    if (entry.loyalty) loyalty[house].push(entry.loyalty);
  }
  // each member's numbers are read against their own chamber's middle
  // half; party agreement only within the session most members are
  // measured on, so a yardstick never mixes sessions
  const sameSession = (rows: { pct: number; session: string }[]) => {
    const counts = new Map<string, number>();
    for (const r of rows) counts.set(r.session, (counts.get(r.session) ?? 0) + 1);
    const session = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    const t = middleHalf(rows.filter((r) => r.session === session).map((r) => r.pct));
    return t && session ? { ...t, session } : null;
  };
  const typical = {
    assembly: { missed: middleHalf(missed.assembly), loyalty: sameSession(loyalty.assembly) },
    senate: { missed: middleHalf(missed.senate), loyalty: sameSession(loyalty.senate) },
  };
  return new Response(JSON.stringify({ assembly, senate, phase: ballotPhase(), typical }), {
    headers: { "Content-Type": "application/json" },
  });
};
