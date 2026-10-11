/** Device-only follows, same model as districts and polling places: the
 * server never learns what anyone follows.
 *
 * Six kinds share one store. Older stores migrate silently: any missing
 * list is simply empty. */
import { store } from "../lib/store.ts";
import { wisconsinToday } from "../lib/today.ts";
import { esc } from "../lib/html.ts";

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
    raw = JSON.parse(store.get(KEY) ?? "null");
  } catch {
    store.remove(KEY);
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
  store.set(KEY, JSON.stringify(follows));
  return at < 0;
}

/** Wisconsin date of the previous visit to /following/, updated on view. */
export function lastSeen(): string | null {
  return store.get(SEEN_KEY);
}

export function markSeen(now = new Date()): void {
  store.set(SEEN_KEY, wisconsinToday(now));
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

/** The kinds with an Atom feed (pipeline/dataproducts/feeds.py), keyed to
 * the feed's path for a follow id. Districts and races have none. */
const FEED_PATHS: [keyof Follows, string, (id: string) => string][] = [
  ["bills", "Bills", (id) => `/feeds/bills/${id}.xml`],
  ["legislators", "State lawmakers", (id) => `/feeds/legislators/${id}.xml`],
  ["committees", "Committees", (id) => `/feeds/committees/${id}.xml`],
  ["council", "City council members", (id) => `/feeds/local/${id}.xml`],
];

/** An OPML file of the feeds for what's followed, for a feed reader to
 * import. `names` ("kind|id" -> name) titles each feed; an unknown name
 * falls back to the id. */
export function followsOpml(follows: Follows, origin: string, names: Map<string, string> = new Map()): string {
  const groups = FEED_PATHS.filter(([kind]) => follows[kind].length).map(([kind, label, path]) =>
    `<outline text="${esc(label)}">` +
    follows[kind].map((id) => {
      const text = esc(names.get(`${kind}|${id}`) ?? id);
      return `<outline type="rss" text="${text}" title="${text}" xmlUrl="${esc(origin + path(id))}"/>`;
    }).join("") +
    `</outline>`);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0"><head><title>Followed on Badger Politics</title></head>` +
    `<body>${groups.join("")}</body></opml>\n`;
}

/** Follows moved between devices ride in a link's fragment, which the
 * browser never sends to the server: "bills:2025-ab1,2025-ab2;races:senate-5".
 * A shared link is untrusted input, so every id must have its kind's exact
 * shape, and anything else rejects the whole link. */
const SLUG = "[a-z0-9][a-z0-9-]{0,99}";
const SEAT = /^(assembly|senate)-[1-9][0-9]?$/;
const ID_SHAPE: Record<keyof Follows, RegExp> = {
  bills: /^[0-9]{4}[a-z0-9-]{0,40}-[a-z0-9]{1,20}$/,
  legislators: new RegExp(`^${SLUG}$`),
  committees: new RegExp(`^${SLUG}$`),
  districts: SEAT,
  races: SEAT,
  council: new RegExp(`^${SLUG}/${SLUG}$`),
};
const MAX_PER_KIND = 500;

export const isFollowId = (kind: keyof Follows, id: string): boolean => ID_SHAPE[kind].test(id);

export const encodeFollows = (follows: Follows): string =>
  FOLLOW_KINDS.map((kind) => [kind, follows[kind].filter((id) => isFollowId(kind, id))] as const)
    .filter(([, ids]) => ids.length)
    .map(([kind, ids]) => `${kind}:${ids.join(",")}`)
    .join(";");

/** The fragment's follow list, or null when any part of it is malformed. */
export function decodeFollows(text: string): Follows | null {
  let raw: string;
  try {
    raw = decodeURIComponent(text);
  } catch {
    return null;
  }
  if (!raw || raw.length > 60_000) return null;
  const out = Object.fromEntries(FOLLOW_KINDS.map((k) => [k, []])) as unknown as Follows;
  const seen = new Set<string>();
  for (const part of raw.split(";")) {
    const at = part.indexOf(":");
    const kind = part.slice(0, at) as keyof Follows;
    if (at < 0 || !FOLLOW_KINDS.includes(kind) || seen.has(kind)) return null;
    seen.add(kind);
    const ids = part.slice(at + 1).split(",");
    if (ids.length > MAX_PER_KIND || !ids.every((id) => isFollowId(kind, id))) return null;
    out[kind] = [...new Set(ids)];
  }
  return out;
}

/** Adds what isn't followed yet; returns how many were new. */
export function mergeFollows(incoming: Follows): number {
  const follows = getFollows();
  let added = 0;
  for (const kind of FOLLOW_KINDS) {
    for (const id of incoming[kind]) {
      if (!follows[kind].includes(id)) {
        follows[kind].push(id);
        added += 1;
      }
    }
  }
  if (added) store.set(KEY, JSON.stringify(follows));
  return added;
}
