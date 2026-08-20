/** Every dated civic event for the interactive calendar: hearings (with
 * links + times) and statewide election days. Regenerated each build. */
import type { APIRoute } from "astro";
import { recentHearings, upcomingHearings } from "../../lib/db";
import { chamberName, fmtTime } from "../../lib/format";

const ELECTION_DAYS: [string, string][] = [
  ["2026-02-17", "Wisconsin Spring Primary"],
  ["2026-04-07", "Wisconsin Spring Election"],
  ["2026-08-11", "Wisconsin Partisan Primary"],
  ["2026-11-03", "Wisconsin General Election"],
];

export const GET: APIRoute = () => {
  type CalEvent = {
    type: string;
    label: string;
    detail?: string;
    url?: string;
    links?: { label: string; url: string }[];
  };
  const events: Record<string, CalEvent[]> = {};
  const add = (date: string, e: CalEvent) => (events[date] ??= []).push(e);

  const seen = new Set<string>();
  for (const h of [...recentHearings(2000), ...upcomingHearings("1900-01-01")]) {
    if (!h.date || seen.has(h.id)) continue;
    seen.add(h.id);
    const name = h.committee_name
      ? `${h.committee_chamber ? `${chamberName(h.committee_chamber)} ` : ""}${h.committee_name}`
      : (h.title ?? "Committee hearing");
    add(h.date, {
      type: "hearing",
      label: name,
      detail: [fmtTime(h.time), h.location].filter(Boolean).join(" · "),
      url: h.source_url ?? undefined,
    });
  }
  for (const [date, label] of ELECTION_DAYS) {
    add(date, {
      type: "election",
      label,
      detail: "Polls open 7 AM – 8 PM",
      links: [
        { label: "Find where you vote", url: "https://myvote.wi.gov/en-us/Find-My-Polling-Place" },
        { label: "What's on my ballot", url: "https://myvote.wi.gov/en-us/My-Voter-Info" },
        { label: "Vote absentee", url: "https://myvote.wi.gov/en-us/Vote-Absentee-Guide" },
      ],
    });
  }
  return new Response(JSON.stringify(events), {
    headers: { "Content-Type": "application/json" },
  });
};
