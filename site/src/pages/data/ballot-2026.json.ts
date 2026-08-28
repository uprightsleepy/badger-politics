/** Per-district ballot lookup for the address-first view on /elections/2026/.
 *
 * The election page lists every statewide office and every legislative
 * seat, which is the complete record but not what one voter is looking
 * for. This lets the page answer "what is on *my* ballot" from the
 * district already saved in the reader's browser, with no account and
 * nothing sent anywhere.
 *
 * Only Approve-status filings are listed as candidates: a filing the
 * Elections Commission has not approved is not yet on a ballot, and
 * showing it as though it were would be wrong.
 */
import type { APIRoute } from "astro";
import { sittingPeople, electionFor, statewideRaces } from "../../lib/db";
import { personSlug } from "../../lib/format";

type Race = {
  district: number;
  onBallot: boolean;
  incumbent: { name: string; party: string | null; slug: string } | null;
  incumbentRunning: boolean;
  candidates: { name: string; party: string | null }[];
};

export const GET: APIRoute = () => {
  const assembly: Record<string, Race> = {};
  const senate: Record<string, Race> = {};

  for (const p of sittingPeople()) {
    const e = electionFor(p.id);
    if (!e || e.cycle_year !== 2026 || p.district == null) continue;
    const race: Race = {
      district: p.district,
      onBallot: e.on_ballot === 1,
      incumbent: { name: p.name, party: p.party, slug: personSlug(p.id) },
      incumbentRunning: e.on_ballot === 1,
      candidates: (e.opponents ?? [])
        .filter((o) => o.ballot_status !== "Deny")
        .map((o) => ({ name: o.name, party: o.party })),
    };
    (p.chamber === "upper" ? senate : assembly)[String(p.district)] = race;
  }

  // Every voter in the state sees these, whatever their district.
  const statewide = statewideRaces()
    .filter((r) => r.ballot_status === "Approve")
    .reduce<Record<string, { name: string; party: string | null }[]>>((acc, r) => {
      (acc[r.office] ??= []).push({ name: r.candidate, party: r.party });
      return acc;
    }, {});

  return new Response(JSON.stringify({ assembly, senate, statewide }), {
    headers: { "Content-Type": "application/json" },
  });
};
