/** Per-sitting-legislator quick-glance data for the client-side my-reps
 * cards: recent roll-call votes, this-biennium attendance and authorship,
 * committees, and ballot status. Device-side lookup only: the page picks
 * the two entries matching the locally saved districts. */
import type { APIRoute } from "astro";
import { sittingPeople, personVotes, committeesFor } from "../../lib/db";
import { legislatorProfile } from "../../lib/legislator";
import { billSlug, committeeSlug, personSlug } from "../../lib/format";
import type { RepSummary } from "../../lib/wire";

export const GET: APIRoute = () => {
  const assembly: Record<string, RepSummary> = {};
  const senate: Record<string, RepSummary> = {};

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
  }
  return new Response(JSON.stringify({ assembly, senate }), {
    headers: { "Content-Type": "application/json" },
  });
};
