/** Device-only follows, same model as districts and polling places: the
 * server never learns what anyone follows.
 *
 * Five kinds share one store. Old two-kind stores migrate silently: any
 * missing list is simply empty. */
export interface Follows {
  bills: string[];
  legislators: string[];
  committees: string[];
  districts: string[];
  races: string[];
}
export const FOLLOW_KINDS = ["bills", "legislators", "committees", "districts", "races"] as const;

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

/** ISO date of the previous visit to /following/, updated on view. */
export function lastSeen(): string | null {
  return localStorage.getItem(SEEN_KEY);
}

export function markSeen(): void {
  localStorage.setItem(SEEN_KEY, new Date().toISOString().slice(0, 10));
}
