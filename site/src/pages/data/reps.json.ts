/** District -> sitting legislator lookup for the client-side my-reps flow. */
import type { APIRoute } from "astro";
import { sittingPeople } from "../../lib/db";
import { personSlug } from "../../lib/format";
import type { RepSlim } from "../../lib/wire";

export const GET: APIRoute = () => {
  const assembly: Record<string, RepSlim> = {};
  const senate: Record<string, RepSlim> = {};
  for (const p of sittingPeople()) {
    const entry: RepSlim = {
      name: p.name,
      party: p.party,
      slug: personSlug(p.id),
      // 131 of 132 sitting members have an official portrait; the odd one
      // out falls back to initials rather than a broken image
      image: p.image_url,
    };
    if (p.chamber === "lower" && p.district != null) assembly[p.district] = entry;
    if (p.chamber === "upper" && p.district != null) senate[p.district] = entry;
  }
  return new Response(JSON.stringify({ assembly, senate }), {
    headers: { "Content-Type": "application/json" },
  });
};
