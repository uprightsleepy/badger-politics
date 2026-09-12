/** One legislator's derived record, shaped once from the db.ts queries:
 * service and attendance, party agreement, authorship, and the seat's
 * ballot status. The profile page, the my-reps summary and the ballot
 * pages read this. Lists with their own paging (votes, key votes, party
 * breaks) stay direct queries. */
import {
  bienniumOf, chamberVoteDays, currentSessions, electionFor, partyAgreement,
  personSponsorships, personVoteDays, termsFor, type Person,
} from "./db.ts";
import {
  attendanceTotals, buildHeatDays, mergeServiceSpans, type HeatDay, type TermRow,
} from "./service.ts";
import { ballotStatus } from "./ballot.ts";

export type Sponsorship = ReturnType<typeof personSponsorships>[number];

export const isSitting = (p: Pick<Person, "current_role">): boolean =>
  p.current_role === "Representative" || p.current_role === "Senator";

/** Bill stages in the order the tally shows them. */
export const TALLY_ORDER = [
  "enacted", "adopted", "vetoed", "passed", "passed_chamber", "in_committee", "introduced",
  "failed_sjr1",
];

/** Wisconsin's three roles: the first name on a bill is its lead author,
 * same-house signers are coauthors, other-house signers are cosponsors.
 * Counts recompute from live statuses every nightly rebuild. */
export const authorship = (sponsorships: Sponsorship[]) => {
  const led = sponsorships.filter((s) => s.role === "lead");
  return {
    led,
    coauthored: sponsorships.filter((s) => s.role === "coauthor"),
    cosponsored: sponsorships.filter((s) => s.role === "cosponsor"),
    enacted: led.filter((s) => s.status === "enacted").length,
    vetoed: led.filter((s) => s.status === "vetoed").length,
    noHearing: led.filter((s) => s.died_without_hearing === 1).length,
    tally: TALLY_ORDER
      .map((status) => ({ status, bills: led.filter((s) => s.status === status) }))
      .filter((t) => t.bills.length > 0),
  };
};

export type AttendanceBlock =
  | { kind: "year"; year: number }
  | { kind: "gap"; from: number; to: number; label: string | null; url: string | null };

/** Years with any in-office voting day get a tile strip; runs of fully
 * out-of-office years collapse into one row naming the event that opened
 * the gap (a recall, a resignation) with its reference. */
const blocksFor = (heatDays: HeatDay[], spans: TermRow[]): AttendanceBlock[] => {
  const year = (d: HeatDay) => Number(d.date.slice(0, 4));
  const years = [...new Set(heatDays.map(year))].sort((a, b) => b - a);
  const served = new Set(heatDays.filter((d) => d.served !== false).map(year));
  const blocks: AttendanceBlock[] = [];
  for (const y of years) {
    if (served.has(y)) {
      blocks.push({ kind: "year", year: y });
      continue;
    }
    const prev = blocks[blocks.length - 1];
    if (prev?.kind === "gap" && prev.from === y + 1) {
      prev.from = y; // years descend, so the run extends downward
      continue;
    }
    const cause = spans
      .filter((s) => s.end && s.end <= `${y + 1}-01-01`)
      .sort((a, b) => (a.end! < b.end! ? 1 : -1))[0];
    blocks.push({
      kind: "gap", from: y, to: y,
      label: cause?.end_label ?? null, url: cause?.end_url ?? null,
    });
  }
  return blocks;
};

/** Agreement is per session, newest first, and a special session can hold
 * a single vote: taking [0] blindly reported "0%" off one roll call. */
const LOYALTY_MIN = 20;

export const legislatorProfile = (person: Person) => {
  const terms = termsFor(person.id);
  const serviceSpans = mergeServiceSpans(terms);
  // A chamber's voting day counts only inside one of this person's terms
  // for that chamber; out-of-office gaps never show as missed votes.
  const heatDays = buildHeatDays(terms, personVoteDays(person.id), chamberVoteDays());
  const blocks = blocksFor(heatDays, serviceSpans);
  const sponsorships = personSponsorships(person.id);
  const agreement = partyAgreement(person.id, person.party);
  const election = electionFor(person.id);
  const sessions = currentSessions();
  const current = new Set(sessions.map((s) => s.id));
  const bienniumStart = sessions.length ? `${bienniumOf(sessions[0].id)}-01-01` : null;
  return {
    sitting: isSitting(person),
    terms,
    serviceSpans,
    heatDays,
    attendance: {
      ...attendanceTotals(heatDays),
      days: heatDays.filter((d) => d.served !== false).length,
      blocks,
      openYears: new Set(blocks.flatMap((b) => (b.kind === "year" ? [b.year] : [])).slice(0, 2)),
    },
    agreement,
    loyalty: agreement.find((a) => a.n >= LOYALTY_MIN) ?? null,
    authorship: authorship(sponsorships),
    election,
    opponents: election?.opponents.filter((o) => o.ballot_status !== "Deny") ?? [],
    ballot: ballotStatus(election),
    /** The newest biennium only, for the my-reps summary. */
    biennium: {
      attendance: attendanceTotals(
        bienniumStart ? heatDays.filter((d) => d.date >= bienniumStart) : [],
      ),
      authorship: authorship(sponsorships.filter((s) => current.has(s.session_id))),
    },
  };
};
export type LegislatorProfile = ReturnType<typeof legislatorProfile>;
