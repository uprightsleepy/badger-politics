/** What a list of bills says about each one: the same status headline and
 * route the bill's own page tells, so a list and a page never disagree.
 * Build time only (reads each bill's official history). */
import { actionsFor, billsFor, meta, type Bill } from "./db.ts";
import { memoBy, once } from "./connection.ts";
import { tellStory, type Stop, type StopKey } from "./billStory.ts";

// judged as of the snapshot, as the bill pages are
const asOf = once(() => (meta().imported_at ?? new Date().toISOString()).slice(0, 10));

export interface RowStory {
  headline: string;
  stops: Stop[];
  stopped: boolean;
  /** The stop the bill is at, or stopped at. */
  here: StopKey;
  /** A public hearing is recorded before its first floor vote. */
  hearing: boolean;
}

const byId = new Map<string, RowStory>();
/** Keyed by bill id: each list query hands back fresh row objects. */
export const rowStory = (bill: Bill): RowStory => {
  const hit = byId.get(bill.id);
  if (hit) return hit;
  const s = tellStory(bill, actionsFor(bill.id), asOf());
  const row: RowStory = {
    headline: s.headline,
    stops: s.stops,
    stopped: s.stopped,
    here: s.stops.find((x) => x.state === "here")?.key ?? s.stops[s.stops.length - 1].key,
    hearing: s.progress.hearing != null,
  };
  byId.set(bill.id, row);
  return row;
};

/** The stored statuses in route order, so views read the way a bill
 * travels rather than by whichever happens to be largest. */
export const STATUS_ORDER = [
  "introduced", "in_committee", "passed_chamber", "passed",
  "enacted", "vetoed", "adopted", "failed_sjr1",
];

export interface SessionCounts {
  total: number;
  byStatus: [string, number][];
  enacted: number;
  vetoed: number;
  /** Died at session end after a referral, with no hearing or committee
   * session ever recorded (the importer's died_without_hearing). Zero
   * until the session's end is recorded. */
  noHearing: number;
}

export const sessionCounts = memoBy((sessionId: string): SessionCounts => {
  const bills = billsFor(sessionId);
  const counts = new Map<string, number>();
  let noHearing = 0;
  for (const b of bills) {
    const key = b.status ?? "introduced";
    counts.set(key, (counts.get(key) ?? 0) + 1);
    if (b.died_without_hearing === 1) noHearing++;
  }
  const rank = (k: string) => {
    const i = STATUS_ORDER.indexOf(k);
    return i < 0 ? STATUS_ORDER.length : i;
  };
  return {
    total: bills.length,
    byStatus: [...counts].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0])),
    enacted: counts.get("enacted") ?? 0,
    vetoed: counts.get("vetoed") ?? 0,
    noHearing,
  };
});

/** "2,749 bills and resolutions. 312 became law, 25 were vetoed, and
 * 1,940 never got a public hearing." Counts of zero are left out rather
 * than shown as a fact: no hearing count exists until the session's end
 * is recorded. */
export const leadSentence = (c: { total: number; enacted: number; vetoed: number; noHearing: number }): string => {
  const n = (x: number) => x.toLocaleString();
  const parts = [
    `${n(c.enacted)} became law`,
    c.vetoed ? `${n(c.vetoed)} ${c.vetoed === 1 ? "was" : "were"} vetoed` : "",
    c.noHearing ? `${n(c.noHearing)} never got a public hearing` : "",
  ].filter(Boolean);
  const list =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(", ")}${parts.length > 2 ? "," : ""} and ${parts.at(-1)}`;
  const total = c.total === 1 ? "1 bill or resolution" : `${n(c.total)} bills and resolutions`;
  return c.total === 0 ? "No bills or resolutions are recorded yet." : `${total}. ${list}.`;
};
export const sessionLead = (sessionId: string): string => leadSentence(sessionCounts(sessionId));

export type OutcomeKey =
  | "law" | "vetoed" | "governor" | "moving"
  | "stopped-governor" | "stopped-other" | "stopped-origin" | "stopped-committee" | "stopped-introduced";

export interface SessionOutcomes {
  /** Bills only: resolutions never go to the governor. */
  bills: number;
  resolutions: number;
  /** Each bill counted once, at the furthest point it reached. */
  counts: Record<OutcomeKey, number>;
  /** Of the bills that stopped in committee, those that died there with no
   * public hearing or committee session (the importer's died_without_hearing). */
  committeeNoHearing: number;
  /** Of the bills that stopped in committee, those whose history records a
   * public hearing. */
  committeeHeard: number;
}

/** How far a session's bills got. Finished outcomes come from the stored
 * status (the same as the status views they link to); everything else is
 * placed where its own page's route places it, so the homepage, the lists
 * and the bill pages agree on every bill. */
export const sessionOutcomes = memoBy((sessionId: string): SessionOutcomes => {
  const counts: Record<OutcomeKey, number> = {
    law: 0, vetoed: 0, governor: 0, moving: 0,
    "stopped-governor": 0, "stopped-other": 0, "stopped-origin": 0,
    "stopped-committee": 0, "stopped-introduced": 0,
  };
  let bills = 0;
  let resolutions = 0;
  let committeeNoHearing = 0;
  let committeeHeard = 0;
  for (const b of billsFor(sessionId)) {
    if (b.classification !== "bill") {
      resolutions++;
      continue;
    }
    bills++;
    if (b.status === "enacted") counts.law++;
    else if (b.status === "vetoed") counts.vetoed++;
    else if (b.status === "passed") counts.governor++;
    else {
      const s = rowStory(b);
      if (!s.stopped) counts.moving++;
      else if (s.here === "governor") counts["stopped-governor"]++;
      else if (s.here === "other") counts["stopped-other"]++;
      else if (s.here === "origin") counts["stopped-origin"]++;
      else if (s.here === "introduced") counts["stopped-introduced"]++;
      else {
        // the committee stop; a bill in these statuses can't have reached
        // the law stop, which needs the governor's signature
        counts["stopped-committee"]++;
        // the importer's definition, the one every "never got a hearing"
        // count on the site uses (see neverHeard)
        if (b.died_without_hearing === 1) committeeNoHearing++;
        if (s.hearing) committeeHeard++;
      }
    }
  }
  return { bills, resolutions, counts, committeeNoHearing, committeeHeard };
});

/** Bills and resolutions that died in committee without a public hearing
 * or a committee session (the importer's died_without_hearing), counted
 * apart, with the totals they're out of. The session lists and
 * /hearing-none/ count exactly this; the homepage counts the flagged bills
 * among those that stopped in committee in their first chamber. */
export const neverHeard = memoBy((sessionId: string) => {
  let bills = 0, resolutions = 0, totalBills = 0, totalResolutions = 0;
  for (const b of billsFor(sessionId)) {
    const heardNone = b.died_without_hearing === 1;
    if (b.classification === "bill") {
      totalBills++;
      if (heardNone) bills++;
    } else {
      totalResolutions++;
      if (heardNone) resolutions++;
    }
  }
  return { bills, resolutions, totalBills, totalResolutions };
});
