/** All dated civic events (hearings + election days) for the calendar page. */
import type { APIRoute } from "astro";
import { allHearings } from "../../lib/db";
import { chamberName, fmtTime } from "../../lib/format";
import ELECTION_DAYS from "../../data/election-days.json";

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

  for (const h of allHearings()) {
    if (!h.date) continue;
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
