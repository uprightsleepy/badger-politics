/** Device-only follows, same model as districts and polling places: the
 * server never learns what anyone follows.
 *
 * Six kinds share one store. Older stores migrate silently: any missing
 * list is simply empty. */
import { wisconsinToday } from "../lib/today.ts";

export interface Follows {
  bills: string[];
  legislators: string[];
  committees: string[];
  districts: string[];
  races: string[];
  council: string[];
}
export const FOLLOW_KINDS = [
  "bills", "legislators", "committees", "districts", "races", "council",
] as const;

const KEY = "bp-follows";
const SEEN_KEY = "bp-follows-seen";

export function getFollows(): Follows {
  let raw: unknown = null;
  try {
    raw = JSON.parse(localStorage.getItem(KEY) ?? "null");
  } catch {
    localStorage.removeItem(KEY);
  }
  const out = {} as Follows;
  for (const kind of FOLLOW_KINDS) {
    const list = (raw as Record<string, unknown> | null)?.[kind];
    out[kind] = Array.isArray(list) ? list.filter((x) => typeof x === "string") : [];
  }
  return out;
}

export function isFollowing(kind: keyof Follows, id: string): boolean {
  return getFollows()[kind].includes(id);
}

export function toggleFollow(kind: keyof Follows, id: string): boolean {
  const follows = getFollows();
  const list = follows[kind];
  const at = list.indexOf(id);
  if (at >= 0) list.splice(at, 1);
  else list.push(id);
  localStorage.setItem(KEY, JSON.stringify(follows));
  return at < 0;
}

/** Wisconsin date of the previous visit to /following/, updated on view. */
export function lastSeen(): string | null {
  return localStorage.getItem(SEEN_KEY);
}

export function markSeen(now = new Date()): void {
  localStorage.setItem(SEEN_KEY, wisconsinToday(now));
}

/** Whether a record dated `date` is news to someone last here on `seen`.
 * Both are Wisconsin dates, so they compare as strings. */
export const isNewSince = (seen: string | null, date: string | null | undefined): boolean =>
  !!(seen && date && date > seen);

/** A committee is news when it held a hearing since the last visit; an
 * upcoming one was already on the list then. */
export const heardSince = (seen: string | null, dates: string[], today: string): boolean =>
  dates.some((d) => isNewSince(seen, d) && d < today);

/** Bill follow ids are "{session}-{slug}"; a special session's key has a
 * hyphen of its own ("2013s-dec"), a bill's slug never does. */
export const splitBillId = (id: string): { session: string; slug: string } => {
  const at = id.lastIndexOf("-");
  return { session: id.slice(0, at), slug: id.slice(at + 1) };
};
