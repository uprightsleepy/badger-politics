/** District -> sitting legislator lookup for the client-side my-reps flow. */
import type { APIRoute } from "astro";
import { sittingPeople } from "../../lib/db";
import { personSlug } from "../../lib/format";

export const GET: APIRoute = () => {
  const assembly: Record<string, unknown> = {};
  const senate: Record<string, unknown> = {};
  for (const p of sittingPeople()) {
    const entry = {
      name: p.name,
      party: p.party,
      slug: personSlug(p.id),
    };
    if (p.chamber === "lower" && p.district != null) assembly[p.district] = entry;
    if (p.chamber === "upper" && p.district != null) senate[p.district] = entry;
  }
  return new Response(JSON.stringify({ assembly, senate }), {
    headers: { "Content-Type": "application/json" },
  });
};
