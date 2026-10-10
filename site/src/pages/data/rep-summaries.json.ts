/** Per-sitting-legislator quick-glance data for the client-side my-reps
 * cards: recent roll-call votes, this-biennium attendance and authorship,
 * committees, and ballot status. Device-side lookup only: the page picks
 * the two entries matching the locally saved districts.
 *
 * It also carries each chamber's yardsticks (the middle half of sitting
 * members on how often they vote and how often they vote with their
 * party), so a single member's number is never shown bare. The same
 * summary and yardsticks feed each lawmaker's own page (lib/repSummary). */
import type { APIRoute } from "astro";
import { sittingPeople, ballotPhase } from "../../lib/db";
import { chamberTypical, repSummary } from "../../lib/repSummary";
import type { RepSummary } from "../../lib/wire";

export const GET: APIRoute = () => {
  const assembly: Record<string, RepSummary> = {};
  const senate: Record<string, RepSummary> = {};
  for (const p of sittingPeople()) {
    if (p.district == null) continue;
    (p.chamber === "upper" ? senate : assembly)[p.district] = repSummary(p);
  }
  return new Response(
    JSON.stringify({ assembly, senate, phase: ballotPhase(), typical: chamberTypical() }),
    { headers: { "Content-Type": "application/json" } },
  );
};
