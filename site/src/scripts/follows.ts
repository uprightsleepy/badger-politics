/** Device-only follows, same model as districts and polling places: the
 * server never learns what anyone follows. */
export interface Follows {
  bills: string[];
  legislators: string[];
}

const KEY = "bp-follows";
const SEEN_KEY = "bp-follows-seen";

export function getFollows(): Follows {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (raw && Array.isArray(raw.bills) && Array.isArray(raw.legislators)) return raw;
  } catch {
    localStorage.removeItem(KEY);
  }
  return { bills: [], legislators: [] };
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
