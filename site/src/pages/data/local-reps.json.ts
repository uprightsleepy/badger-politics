/** City-council roster per covered tenant, for the my-reps card: which
 * alderpersons hold each district, with their page slugs. */
import type { APIRoute } from "astro";
import { localBodies, localMembers } from "../../lib/db";
import type { LocalReps } from "../../lib/wire";

export const GET: APIRoute = () => {
  const out: LocalReps = {};
  for (const body of localBodies()) {
    const districts: Record<string, { name: string; slug: string; image: string | null }[]> = {};
    for (const m of localMembers(body.tenant)) {
      if (!m.is_current || m.seat == null) continue;
      (districts[String(m.seat)] ??= []).push({ name: m.name, slug: m.slug, image: m.image_url });
    }
    out[body.tenant] = {
      city: body.city,
      slug: body.slug,
      council: body.name,
      districts,
    };
  }
  return new Response(JSON.stringify(out), {
    headers: { "Content-Type": "application/json" },
  });
};
