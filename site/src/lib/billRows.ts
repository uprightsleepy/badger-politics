/** What a list of bills says about each one: the same status headline and
 * route the bill's own page tells, so a list and a page never disagree.
 * Build time only (reads each bill's official history). */
import { actionsFor, billsFor, meta, type Bill } from "./db.ts";
import { memoBy, once } from "./connection.ts";
import { tellStory, type Stop } from "./billStory.ts";

// judged as of the snapshot, as the bill pages are
const asOf = once(() => (meta().imported_at ?? new Date().toISOString()).slice(0, 10));

export interface RowStory {
  headline: string;
  stops: Stop[];
  stopped: boolean;
}

const byId = new Map<string, RowStory>();
/** Keyed by bill id: each list query hands back fresh row objects. */
export const rowStory = (bill: Bill): RowStory => {
  const hit = byId.get(bill.id);
  if (hit) return hit;
  const s = tellStory(bill, actionsFor(bill.id), asOf());
  const row = { headline: s.headline, stops: s.stops, stopped: s.stopped };
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
