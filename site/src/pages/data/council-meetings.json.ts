/** Upcoming council meetings per covered tenant. The calendar merges a
 * city's meetings only for readers whose saved address lookup landed in
 * that city; without a saved address none are shown. */
import type { APIRoute } from "astro";
import { localUpcomingMeetings } from "../../lib/db";

type Wire = Record<
  string,
  { city: string; meetings: { date: string; time: string | null; location: string | null; url: string }[] }
>;

export const GET: APIRoute = () => {
  const out: Wire = {};
  for (const m of localUpcomingMeetings()) {
    (out[m.tenant] ??= { city: m.city, meetings: [] }).meetings.push({
      date: m.date, time: m.time, location: m.location, url: m.insite_url,
    });
  }
  return new Response(JSON.stringify(out), {
    headers: { "Content-Type": "application/json" },
  });
};
