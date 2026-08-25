/** Per-sitting-legislator quick-glance data for the client-side my-reps
 * cards: recent roll-call votes, this-biennium attendance and authorship,
 * committees, and ballot status. Device-side lookup only — the page picks
 * the two entries matching the locally saved districts. */
import type { APIRoute } from "astro";
import {
  sittingPeople,
  personVotes,
  personSponsorships,
  personVoteDays,
  chamberVoteDays,
  termsFor,
  committeesFor,
  electionFor,
  currentSessions,
} from "../../lib/db";
import { billSlug, committeeSlug, personSlug } from "../../lib/format";
import { buildHeatDays } from "../../lib/service";

export const GET: APIRoute = () => {
  const sessionIds = new Set(currentSessions().map((s) => s.id));
  const bienniumStart = "2025-01-01";
  const assembly: Record<string, unknown> = {};
  const senate: Record<string, unknown> = {};

  for (const p of sittingPeople()) {
    const heat = buildHeatDays(termsFor(p.id), personVoteDays(p.id), chamberVoteDays())
      .filter((d) => d.date >= bienniumStart && d.served !== false);
    const totalVotes = heat.reduce((s, d) => s + d.total, 0);
    const missedVotes = heat.reduce((s, d) => s + Math.max(0, d.total - d.cast - d.nv), 0);

    const authored = personSponsorships(p.id).filter(
      (s) => s.is_primary && sessionIds.has(s.session_id),
    );
    const election = electionFor(p.id);

    const entry = {
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
      attendance: { total: totalVotes, missed: missedVotes },
      authored: {
        total: authored.length,
        enacted: authored.filter((s) => s.status === "enacted").length,
        vetoed: authored.filter((s) => s.status === "vetoed").length,
        noHearing: authored.filter((s) => s.died_without_hearing === 1).length,
      },
      election: election
        ? { cycle_year: election.cycle_year, on_ballot: election.on_ballot }
        : null,
      recentVotes: personVotes(p.id, 5).map((v) => ({
        date: v.date,
        option: v.option,
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
