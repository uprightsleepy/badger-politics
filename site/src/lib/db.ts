/** Build-time SQLite access. Runs only during `astro build`, never in the
 * browser. BUILD_SESSIONS (comma-separated session ids) limits which
 * sessions render; default is the current biennium. `all` renders history
 * (Phase 6 merges a prebuilt historical artifact instead). */
import Database from "better-sqlite3";
import { resolve } from "node:path";
import { OPEN_END, OPEN_START } from "./sentinels";

// Resolved from the working directory (always site/ for astro and the
// verify scripts), not from import.meta.url: the bundler decides how
// deeply this module is chunked, so a module-relative path silently
// moves with it.
const DB_PATH = resolve(process.cwd(), "../data/wi.sqlite");
const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });

// better-sqlite3 has no implicit statement cache: each prepare() is a full
// SQL compile. One compiled statement per SQL string serves the whole build.
const _stmts = new Map<string, Database.Statement>();
const prep = (sql: string): Database.Statement => {
  let s = _stmts.get(sql);
  if (!s) {
    s = db.prepare(sql);
    _stmts.set(sql, s);
  }
  return s;
};

/** Build-time memoization. The database is read-only for the whole build,
 * so anything derived from it is computed once and shared by every page.
 * `once` for parameterless derivations, `memoBy` for keyed ones. */
const once = <T>(compute: () => T): (() => T) => {
  let value: T;
  let done = false;
  return () => {
    if (!done) {
      value = compute();
      done = true;
    }
    return value;
  };
};
const memoBy = <K, V>(compute: (key: K) => V): ((key: K) => V) => {
  const cache = new Map<K, V>();
  return (key) => {
    if (!cache.has(key)) cache.set(key, compute(key));
    return cache.get(key)!;
  };
};

/** Enrichment tables are absent from older snapshots; their readers
 * degrade to "nothing" rather than failing the build. */
const hasTable = memoBy(
  (name: string) =>
    !!prep("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?").get(name),
);

export interface Session {
  id: string;
  identifier: string;
  name: string | null;
  data_quality: string | null;
}
export interface Bill {
  id: string;
  session_id: string;
  identifier: string;
  title: string | null;
  chamber: string | null;
  classification: string | null;
  status: string | null;
  latest_action_date: string | null;
  latest_action_desc: string | null;
  text_url: string | null;
  lrb_analysis: string | null;
  died_without_hearing: number;
  committee_at_death: string | null;
  committee_chair_at_death: string | null;
}
export interface Person {
  id: string;
  name: string;
  party: string | null;
  current_role: string | null;
  chamber: string | null;
  district: number | null;
  image_url: string | null;
  email: string | null;
  office_phone: string | null;
  office_address: string | null;
  contact_url: string | null;
}

// order by real start (first recorded action), newest first: special-session
// ids like '2013s-oct' would otherwise sort alphabetically, not by month
export const allSessions = once(
  (): Session[] =>
    prep(
      `SELECT s.*, (SELECT MIN(a.date) FROM actions a JOIN bills b ON b.id = a.bill_id
         WHERE b.session_id = s.id) AS first_action
       FROM sessions s ORDER BY first_action DESC, s.id DESC`,
    ).all() as Session[],
);

// BUILD_SESSIONS cannot change mid-build
export const builtSessions = once((): Session[] => {
  const env = process.env.BUILD_SESSIONS ?? "2025,2026s1";
  const sessions = allSessions();
  if (env === "all") return sessions;
  const wanted = new Set(env.split(",").map((s) => s.trim()));
  return sessions.filter((s) => wanted.has(s.id));
});

// one query serves every page's layout
export const meta = once(
  (): Record<string, string> =>
    Object.fromEntries(
      (prep("SELECT key, value FROM meta").all() as { key: string; value: string }[]).map(
        (r) => [r.key, r.value],
      ),
    ),
);

/** The bill's officially declared companions: the same legislation
 * introduced in the other chamber. The edge comes from docs.legis's own
 * "See Also" cross-reference, never from matching titles -- 2025's AB 1
 * pairs with SB 18, which title-matching would have gotten wrong. The
 * table only exists after enrichment, so absence degrades to "no
 * companions" rather than a build failure. */
export const companionsFor = (billId: string) => {
  if (!hasTable("bill_companions")) return [];
  return prep(
      `SELECT b.id, b.identifier, b.session_id, b.status, bc.source_url
       FROM bill_companions bc JOIN bills b ON b.id = bc.companion_bill_id
       WHERE bc.bill_id = ? ORDER BY b.identifier`,
    )
    .all(billId) as {
    id: string; identifier: string; session_id: string; status: string | null;
    source_url: string;
  }[];
};

/** Wisconsin's federal delegation and the U.S. Senate roll calls, from
 * the senate.gov XML the pipeline mirrors. The tables are an enrichment:
 * when they are absent (an older snapshot), everything degrades to empty
 * and the federal pages simply do not build. */
const hasFederal = () => hasTable("federal_members");

export interface FederalMember {
  bioguide: string; lis_id: string | null; name: string; slug: string;
  party: string; chamber: string; district: number | null;
  term_start: string; term_end: string;
}
export const federalMembers = (): FederalMember[] =>
  hasFederal()
    ? (prep("SELECT * FROM federal_members ORDER BY chamber DESC, district").all() as FederalMember[])
    : [];

/** memberKey is the LIS id for senators, the bioguide for House members
 * -- whichever id that chamber's own files stamp on each position. */
export const federalVotesFor = (memberKey: string) =>
  prep(
      `SELECT v.*, r.vote_cast FROM federal_votes v
       JOIN federal_vote_records r ON r.vote_id = v.id
       WHERE r.member_id = ?
       ORDER BY v.date DESC, v.number DESC`,
    )
    .all(memberKey) as {
    id: string; congress: number; session: number; number: number; date: string;
    question: string | null; result: string | null; title: string | null;
    yeas: number; nays: number; majority_requirement: string | null;
    document: string | null; source_url: string; vote_cast: string;
  }[];

/** Per-Congress totals for one senator: cast next to missed, the
 * "how are they representing us" summary in four columns. */
export const federalCongressStats = (memberKey: string) =>
  prep(
      `SELECT v.congress, COUNT(*) AS total,
              SUM(r.vote_cast = 'Not Voting') AS missed,
              MIN(v.date) AS first, MAX(v.date) AS last
       FROM federal_votes v JOIN federal_vote_records r ON r.vote_id = v.id
       WHERE r.member_id = ?
       GROUP BY v.congress ORDER BY v.congress DESC`,
    )
    .all(memberKey) as { congress: number; total: number; missed: number; first: string; last: string }[];

export const federalLatestVoteDate = (): string | null =>
  hasFederal()
    ? ((prep("SELECT MAX(date) AS d FROM federal_votes").get() as { d: string | null }).d)
    : null;

export const billsFor = (sessionId: string): Bill[] =>
  prep("SELECT * FROM bills WHERE session_id = ? AND source != 'legiscan' ORDER BY id")
    .all(sessionId) as Bill[];

export const actionsFor = (billId: string) =>
  prep(
      "SELECT date, chamber, description, classification FROM actions WHERE bill_id = ? ORDER BY date, id",
    )
    .all(billId) as { date: string; chamber: string | null; description: string; classification: string }[];

export const sponsorsFor = (billId: string) =>
  prep(
      `SELECT s.name, s.person_id, s.is_primary, p.party, p.district, p.chamber
       FROM sponsorships s LEFT JOIN people p ON p.id = s.person_id
       WHERE s.bill_id = ? ORDER BY s.is_primary DESC, s.name`,
    )
    .all(billId) as {
    name: string;
    person_id: string | null;
    is_primary: number;
    party: string | null;
    district: number | null;
    chamber: string | null;
  }[];

export const votesFor = (billId: string) =>
  prep("SELECT * FROM vote_events WHERE bill_id = ? ORDER BY date, id")
    .all(billId) as VoteEvent[];

export interface VoteEvent {
  id: string;
  bill_id: string;
  date: string | null;
  chamber: string | null;
  motion: string | null;
  result: string | null;
  yes_count: number | null;
  no_count: number | null;
  nv_count: number | null;
  source_url: string | null;
}

export const voteRecordsFor = (voteEventId: string) =>
  prep(
      `SELECT r.option, p.id AS person_id, p.name, p.party, p.district, p.chamber
       FROM vote_records r JOIN people p ON p.id = r.person_id
       WHERE r.vote_event_id = ? ORDER BY p.name`,
    )
    .all(voteEventId) as {
    option: string;
    person_id: string;
    name: string;
    party: string | null;
    district: number | null;
    chamber: string | null;
  }[];

export const people = (): Person[] =>
  prep("SELECT * FROM people ORDER BY name").all() as Person[];

// the district pages ask for the roster once per seat
export const sittingPeople = once(
  (): Person[] =>
    prep(
      "SELECT * FROM people WHERE current_role IN ('Representative', 'Senator') ORDER BY chamber, district",
    ).all() as Person[],
);

/** One member's roll calls, newest first. The profile takes a bounded
 * preview and the paged record pages take slices, so counting and
 * slicing happen in SQLite and a build never holds a whole career in
 * memory. */
export const personVotes = (personId: string, limit: number, offset = 0) =>
  prep(
      `SELECT r.option, e.id AS vote_event_id, e.date, e.motion, e.result,
              b.id AS bill_id, b.identifier, b.title, b.session_id
       FROM vote_records r
       JOIN vote_events e ON e.id = r.vote_event_id
       JOIN bills b ON b.id = e.bill_id
       WHERE r.person_id = ? ORDER BY e.date DESC, e.id LIMIT ? OFFSET ?`,
    )
    .all(personId, limit, offset) as {
    option: string;
    vote_event_id: string;
    date: string | null;
    motion: string | null;
    result: string | null;
    bill_id: string;
    identifier: string;
    title: string | null;
    session_id: string;
  }[];

export const personVoteCount = (personId: string): number =>
  (prep("SELECT COUNT(*) AS n FROM vote_records WHERE person_id = ?").get(personId) as {
    n: number;
  }).n;

/** bill id -> its lead author. The introduction line's order is the
 * Legislature's own ranking (its author index prints a description "only
 * under the first and second author"), and the scraper preserves that
 * order, so the first-listed primary sponsor is the lead author. One scan
 * serves every legislator page. */
const leadAuthors = once((): Map<string, string | null> => {
  const leads = new Map<string, string | null>();
  const rows = prep(
    "SELECT bill_id, person_id FROM sponsorships WHERE is_primary = 1 ORDER BY rowid",
  ).all() as { bill_id: string; person_id: string | null }[];
  for (const r of rows) {
    if (!leads.has(r.bill_id)) leads.set(r.bill_id, r.person_id);
  }
  return leads;
});

/** Every bill a member's name is on, newest first, each tagged with one of
 * the three official roles: lead author (first on the bill), coauthor
 * (same house, signed on), cosponsor (the other house). The profile reads
 * the whole list; the paged record pages take slices (a negative limit is
 * SQLite's "no limit"). */
export const personSponsorships = (personId: string, limit = -1, offset = 0) => {
  const leads = leadAuthors();
  const rows = prep(
      `SELECT s.is_primary, s.classification, b.id AS bill_id, b.identifier,
              b.title, b.status, b.session_id, b.died_without_hearing
       FROM sponsorships s JOIN bills b ON b.id = s.bill_id
       WHERE s.person_id = ? AND b.source != 'legiscan'
       ORDER BY b.id DESC LIMIT ? OFFSET ?`,
    )
    .all(personId, limit, offset) as {
    is_primary: number;
    classification: string;
    bill_id: string;
    identifier: string;
    title: string | null;
    status: string | null;
    session_id: string;
    died_without_hearing: number;
  }[];
  return rows.map((r) => ({
    ...r,
    role: leads.get(r.bill_id) === personId
      ? "lead"
      : r.classification === "cosponsor"
        ? "cosponsor"
        : "coauthor",
  }));
};

export const personSponsorshipCount = (personId: string): number =>
  (prep(
      "SELECT COUNT(*) AS n FROM sponsorships s JOIN bills b ON b.id = s.bill_id" +
        " WHERE s.person_id = ? AND b.source != 'legiscan'",
    ).get(personId) as { n: number }).n;

export const electionFor = memoBy((personId: string) => {
  const row = prep("SELECT * FROM elections WHERE person_id = ?")
    .get(personId) as
    | {
        cycle_year: number;
        office: string;
        district: number;
        on_ballot: number | null;
        opponents_json: string | null;
      }
    | undefined;
  if (!row) return undefined;
  return {
    ...row,
    opponents: JSON.parse(row.opponents_json ?? "[]") as {
      name: string;
      party: string;
      ballot_status: string;
    }[],
  };
});

export const graveyardFor = (sessionId: string) =>
  prep(
      `SELECT committee_at_death, committee_chair_at_death, COUNT(*) AS n
       FROM bills WHERE session_id = ? AND died_without_hearing = 1
       GROUP BY committee_at_death, committee_chair_at_death ORDER BY n DESC`,
    )
    .all(sessionId) as {
    committee_at_death: string | null;
    committee_chair_at_death: string | null;
    n: number;
  }[];

export const graveyardBills = (sessionId: string, committee: string | null) =>
  prep(
      `SELECT id, identifier, title FROM bills
       WHERE session_id = ? AND died_without_hearing = 1
       AND committee_at_death IS ? ORDER BY id`,
    )
    .all(sessionId, committee) as { id: string; identifier: string; title: string | null }[];

const HEARING_SELECT = `SELECT h.*, c.name AS committee_name, c.chamber AS committee_chamber,
       p.name AS chair_name, c.chair_person_id AS chair_person_id,
       v.url AS video_url
       FROM hearings h LEFT JOIN committees c ON c.id = h.committee_id
       LEFT JOIN people p ON p.id = c.chair_person_id
       LEFT JOIN hearing_videos v ON v.hearing_id = h.id`;

export const upcomingHearings = (since: string) =>
  prep(`${HEARING_SELECT} WHERE h.date >= ? ORDER BY h.date, h.time`)
    .all(since) as Hearing[];

export const recentHearings = (limit: number) =>
  prep(`${HEARING_SELECT} ORDER BY h.date DESC, h.time DESC LIMIT ?`)
    .all(limit) as Hearing[];

export const allHearings = () =>
  prep(`${HEARING_SELECT} ORDER BY h.date, h.time`).all() as Hearing[];

/** 'AB 656' -> its bill row in the newest built session that has it. */
export const findBillByIdentifier = memoBy((identifier: string) => {
  const built = builtSessions().map((s) => s.id);
  const rows = prep(
      `SELECT id, session_id FROM bills WHERE identifier = ?
       AND session_id IN (${built.map(() => "?").join(",")})`,
    )
    .all(identifier, ...built) as { id: string; session_id: string }[];
  // builtSessions() is newest first
  rows.sort((a, b) => built.indexOf(a.session_id) - built.indexOf(b.session_id));
  return rows[0] ?? null;
});

export interface Hearing {
  id: string;
  title: string | null;
  committee_id: string | null;
  date: string | null;
  time: string | null;
  location: string | null;
  agenda_bill_ids_json: string;
  source_url: string | null;
  committee_name: string | null;
  committee_chamber: string | null;
  chair_name: string | null;
  chair_person_id: string | null;
  video_url: string | null;
}

/** Exact-name profile resolver: returns a person id only when exactly one
 * person carries the name; ambiguity or no match stays unlinked. */
const nameToId = once(() => {
  const index = new Map<string, string | null>();
  for (const p of prep("SELECT id, name FROM people").all() as { id: string; name: string }[]) {
    index.set(p.name, index.has(p.name) ? null : p.id);
  }
  return index;
});
export const personIdByName = (name: string | null): string | null =>
  name ? (nameToId().get(name) ?? null) : null;

export const recentlyActedBills = (sessionIds: string[], limit = 8) =>
  prep(
      `SELECT * FROM bills WHERE session_id IN (${sessionIds.map(() => "?").join(",")})
       AND classification = 'bill' ORDER BY latest_action_date DESC LIMIT ?`,
    )
    .all(...sessionIds, limit) as Bill[];

/** Days each chamber held attributed floor votes: (chamber, date) -> count.
 * One scan serves every legislator page in the build. */
export const chamberVoteDays = once(
  () =>
    prep(
      `SELECT chamber, date, COUNT(*) AS n FROM vote_events
       WHERE date IS NOT NULL AND chamber IN ('lower', 'upper')
       AND id IN (SELECT DISTINCT vote_event_id FROM vote_records)
       GROUP BY chamber, date`,
    ).all() as { chamber: string; date: string; n: number }[],
);

/** One person's per-day participation: cast = aye/nay, nv = present-not-voting. */
export const personVoteDays = (personId: string) =>
  prep(
      `SELECT e.date, e.chamber,
              SUM(CASE WHEN r.option IN ('yes', 'no') THEN 1 ELSE 0 END) AS cast,
              SUM(CASE WHEN r.option NOT IN ('yes', 'no') THEN 1 ELSE 0 END) AS nv
       FROM vote_records r JOIN vote_events e ON e.id = r.vote_event_id
       WHERE r.person_id = ? AND e.date IS NOT NULL
       GROUP BY e.date, e.chamber`,
    )
    .all(personId) as { date: string; chamber: string; cast: number; nv: number }[];

/** Each party's Aye/Nay split on every roll call, keyed "event|party",
 * and the majority position it implies (ties carry no majority). One
 * scan serves every legislator and roll-call page. */
const partyPositions = once(() => {
  const rows = prep(
      `SELECT r.vote_event_id, p.party, r.option, COUNT(*) AS n
       FROM vote_records r JOIN people p ON p.id = r.person_id
       WHERE r.option IN ('yes', 'no') AND p.party IN ('Democratic', 'Republican')
       GROUP BY r.vote_event_id, p.party, r.option`,
    )
    .all() as { vote_event_id: string; party: string; option: string; n: number }[];
  const splits = new Map<string, { yes: number; no: number }>();
  for (const row of rows) {
    const key = `${row.vote_event_id}|${row.party}`;
    const c = splits.get(key) ?? { yes: 0, no: 0 };
    c[row.option as "yes" | "no"] += row.n;
    splits.set(key, c);
  }
  const majority = new Map<string, string>();
  for (const [key, c] of splits) {
    if (c.yes !== c.no) majority.set(key, c.yes > c.no ? "yes" : "no");
  }
  return { splits, majority };
});

/** Votes where this member's Aye/Nay opposed their own party's majority
 * position on the roll call (ties excluded, absences never counted). */
export const partyBreaks = (personId: string, party: string | null) => {
  if (party !== "Democratic" && party !== "Republican") return [];
  const { majority: majorities, splits } = partyPositions();
  const votes = prep(
      `SELECT r.option, e.id AS vote_event_id, e.date, e.motion, e.source_url,
              b.id AS bill_id, b.identifier, b.title, b.session_id
       FROM vote_records r
       JOIN vote_events e ON e.id = r.vote_event_id
       JOIN bills b ON b.id = e.bill_id
       WHERE r.person_id = ? AND r.option IN ('yes', 'no')
       ORDER BY e.date DESC, e.id`,
    )
    .all(personId) as {
    option: string; vote_event_id: string; date: string | null; motion: string | null;
    source_url: string | null; bill_id: string; identifier: string;
    title: string | null; session_id: string;
  }[];
  return votes
    .filter((v) => {
      const majority = majorities.get(`${v.vote_event_id}|${party}`);
      return majority !== undefined && majority !== v.option;
    })
    .map((v) => ({ ...v, split: splits.get(`${v.vote_event_id}|${party}`)! }));
};

/** Per-party Aye/Nay splits for one roll call, for the party-line /
 * bipartisan tag. Null when either party cast no recorded Aye/Nay. */
export const voteSplit = (voteEventId: string) => {
  const { splits } = partyPositions();
  const dem = splits.get(`${voteEventId}|Democratic`);
  const rep = splits.get(`${voteEventId}|Republican`);
  if (!dem || !rep) return null;
  const dir = (c: { yes: number; no: number }) =>
    c.yes === c.no ? null : c.yes > c.no ? "yes" : "no";
  const d = dir(dem);
  const r = dir(rep);
  return {
    dem, rep,
    label: d === null || r === null ? null : d === r ? "Bipartisan" : "Party-line",
  };
};

/** Sessions of the newest biennium, regardless of BUILD_SESSIONS. */
export const currentSessions = (): Session[] => {
  const sessions = allSessions();
  const newest = Math.max(...sessions.map((s) => bienniumOf(s.id)));
  return sessions.filter((s) => bienniumOf(s.id) === newest);
};

/** Bills before (or past) the governor this biennium, plus veto-override
 * roll calls, straight from official statuses. Bills only: resolutions
 * pass without ever going to the governor. */
export const governorsDesk = () => {
  const ids = currentSessions().map((s) => s.id);
  const marks = ids.map(() => "?").join(",");
  const byStatus = (status: string) =>
    prep(
      `SELECT id, session_id, identifier, title, latest_action_date, latest_action_desc
       FROM bills WHERE session_id IN (${marks}) AND status = ?
       AND classification = 'bill' AND source != 'legiscan'
       ORDER BY latest_action_date DESC, id`,
    ).all(...ids, status) as {
      id: string; session_id: string; identifier: string; title: string | null;
      latest_action_date: string | null; latest_action_desc: string | null;
    }[];
  const overrides = prep(
      `SELECT e.id, e.bill_id, e.date, e.chamber, e.motion, e.result,
              e.yes_count, e.no_count, e.source_url,
              b.identifier, b.title, b.session_id
       FROM vote_events e JOIN bills b ON b.id = e.bill_id
       WHERE b.session_id IN (${marks}) AND e.motion LIKE '%NOTWITHSTANDING%'
       ORDER BY e.date DESC, e.id`,
    ).all(...ids) as {
      id: string; bill_id: string; date: string | null; chamber: string | null;
      motion: string | null; result: string | null; yes_count: number | null;
      no_count: number | null; source_url: string | null;
      identifier: string; title: string | null; session_id: string;
    }[];
  return {
    awaiting: byStatus("passed"),
    enacted: byStatus("enacted"),
    vetoed: byStatus("vetoed"),
    overrides,
  };
};

/** The sitting governor, entirely from certified data: identity and 2026
 * candidacy from the WEC ballot-access report, last election from the
 * certified canvass. Party comes from the winning ticket, never assumed. */
export const governorInfo = () => {
  const row = prep(
      `SELECT incumbent, MAX(incumbent_noncandidacy) AS noncandidacy
       FROM statewide_races WHERE office = 'GOVERNOR' AND incumbent IS NOT NULL`,
    ).get() as { incumbent: string | null; noncandidacy: number } | undefined;
  if (!row?.incumbent) return null;
  const results = prep(
      `SELECT year, candidate, party, votes, total_cast FROM statewide_history
       WHERE office = 'GOVERNOR / LIEUTENANT GOVERNOR'
       AND year = (SELECT MAX(year) FROM statewide_history
                   WHERE office = 'GOVERNOR / LIEUTENANT GOVERNOR')
       ORDER BY votes DESC`,
    ).all() as {
      year: number; candidate: string; party: string | null;
      votes: number; total_cast: number;
    }[];
  const won = results.find((r) => r.candidate.includes(row.incumbent!)) ?? null;
  const runnerUp = results.filter((r) => r !== won)[0] ?? null;
  const candidates2026 = prep(
      `SELECT candidate, party, ballot_status FROM statewide_races
       WHERE office = 'GOVERNOR' ORDER BY candidate`,
    ).all() as { candidate: string; party: string | null; ballot_status: string | null }[];
  return {
    name: row.incumbent,
    party: won?.party ?? null,
    notRunning: row.noncandidacy === 1,
    lastElection: won
      ? { year: won.year, ticket: won.candidate, votes: won.votes,
          total: won.total_cast, runnerUp }
      : null,
    candidates2026,
  };
};

/** Everyone who has held one seat, newest first: term rows joined to
 * people, straight from the Legislature's service records. */
export const seatTerms = (chamber: string, district: number) =>
  prep(
      `SELECT t.person_id, p.name, p.party, p.current_role, t.start, t.end,
              t.end_label, t.end_url
       FROM person_terms t JOIN people p ON p.id = t.person_id
       WHERE t.chamber = ? AND t.district = ? ORDER BY t.start`,
    )
    .all(chamber, district) as {
    person_id: string; name: string; party: string | null; current_role: string | null;
    start: string; end: string | null; end_label: string | null; end_url: string | null;
  }[];

/** Per-session name resolution for display linking: every printed form
 * (surname, compound surname, initial-first, full name) of each member
 * serving that session's biennium, per chamber. A form shared by two
 * members maps to null and never links: exact-unique or nothing. */
export const sessionNameIndex = memoBy((sessionId: string) => {
  const by = bienniumOf(sessionId);
  const start = `${by}-01-01`;
  const end = `${by + 2}-01-01`;
  const rows = prep(
      `SELECT DISTINCT t.person_id, t.chamber, p.name
       FROM person_terms t JOIN people p ON p.id = t.person_id
       WHERE t.start < ? AND ? < COALESCE(t.end, '9999')`,
    )
    .all(end, start) as { person_id: string; chamber: string; name: string }[];
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z]/g, "");
  const index: Record<string, Map<string, string | null>> = { lower: new Map(), upper: new Map() };
  for (const r of rows) {
    const map = index[r.chamber];
    if (!map) continue;
    const words = r.name.split(/\s+/);
    const first = words[0];
    const family = words[words.length - 1];
    const forms = new Set([r.name, family, `${first[0]}. ${family}`]);
    if (words.length >= 3) {
      const compound = words.slice(-2).join(" ");
      forms.add(compound);
      forms.add(`${first[0]}. ${compound}`);
    }
    for (const form of forms) {
      const key = norm(form);
      map.set(key, map.has(key) && map.get(key) !== r.person_id ? null : r.person_id);
    }
  }
  return index;
});

/** Statewide constitutional races from the WEC ballot-access report. */
export const statewideRaces = () =>
  prep("SELECT * FROM statewide_races ORDER BY office, candidate").all() as {
    office: string; incumbent: string | null; incumbent_noncandidacy: number;
    candidate: string; party: string | null; ballot_status: string | null;
  }[];

/** Certified statewide general-election results (WEC canvasses). */
export const statewideHistory = () =>
  prep(
      "SELECT * FROM statewide_history ORDER BY year DESC, office, votes DESC",
    ).all() as {
    year: number; office: string; candidate: string;
    party: string | null; votes: number;
  }[];

// chair, then co-chair, then vice-chair, then rank-and-file
const ROLE_ORDER =
  "CASE WHEN m.role = 'chair' THEN 0 WHEN m.role LIKE 'co-chair%' THEN 1 WHEN m.role LIKE 'vice%' THEN 2 ELSE 3 END";

/** One person's committee assignments, chairs first. */
export const committeesFor = (personId: string) =>
  prep(
      `SELECT c.id, c.name, m.role FROM committee_members m
       JOIN committees c ON c.id = m.committee_id
       WHERE m.person_id = ?
       ORDER BY ${ROLE_ORDER}, c.name`,
    )
    .all(personId) as { id: string; name: string; role: string }[];

/** Lobbying rollups over registrations already linked to bills. */
export const lobbyingOrgs = () =>
  prep(
      `SELECT principal_id AS id, MAX(principal) AS name,
              COUNT(DISTINCT bill_id) AS bills
       FROM lobbying_interests GROUP BY principal_id ORDER BY bills DESC, name`,
    )
    .all() as { id: number; name: string; bills: number }[];

export const mostLobbiedBills = (sessionId: string, limit: number) =>
  prep(
      `SELECT b.id, b.identifier, b.title, b.status, COUNT(*) AS orgs
       FROM lobbying_interests l JOIN bills b ON b.id = l.bill_id
       WHERE b.session_id = ? AND b.source != 'legiscan'
       GROUP BY b.id ORDER BY orgs DESC, b.id LIMIT ?`,
    )
    .all(sessionId, limit) as {
    id: string; identifier: string; title: string | null;
    status: string | null; orgs: number;
  }[];

export const orgLobbying = (principalId: number) =>
  prep(
      `SELECT l.bill_id, l.principal, l.source_url, b.identifier, b.title,
              b.status, b.session_id
       FROM lobbying_interests l JOIN bills b ON b.id = l.bill_id
       WHERE l.principal_id = ? AND b.source != 'legiscan'
       ORDER BY b.session_id DESC, b.id`,
    )
    .all(principalId) as {
    bill_id: string; principal: string; source_url: string | null;
    identifier: string; title: string | null; status: string | null; session_id: string;
  }[];

/** Share of a member's aye/nay floor votes matching their party's majority
 * position, per session. Presented as a plain number, never a grade. */
export const partyAgreement = (personId: string, party: string | null) => {
  if (party !== "Democratic" && party !== "Republican") return [];
  const { majority: majorities } = partyPositions();
  const votes = prep(
      `SELECT r.vote_event_id, r.option, b.session_id
       FROM vote_records r
       JOIN vote_events e ON e.id = r.vote_event_id
       JOIN bills b ON b.id = e.bill_id
       WHERE r.person_id = ? AND r.option IN ('yes', 'no')`,
    )
    .all(personId) as { vote_event_id: string; option: string; session_id: string }[];
  const bySession = new Map<string, { agree: number; total: number }>();
  for (const v of votes) {
    const majority = majorities.get(`${v.vote_event_id}|${party}`);
    if (!majority) continue;
    const s = bySession.get(v.session_id) ?? { agree: 0, total: 0 };
    s.total += 1;
    if (v.option === majority) s.agree += 1;
    bySession.set(v.session_id, s);
  }
  return [...bySession.entries()]
    .map(([session, s]) => ({ session, pct: (s.agree / s.total) * 100, n: s.total }))
    .sort((a, b) => (a.session < b.session ? 1 : -1));
};

/** Official WEC general-election results for one seat, newest first.
 * Percentages use the canvass's own Total Votes Cast where present, so
 * they match the certified report exactly. */
export const electionHistoryFor = (chamber: string | null, district: number | null) =>
  !chamber || district == null ? [] : electionHistoryBySeat(`${chamber}|${district}`);

const electionHistoryBySeat = memoBy((seat: string) => {
  const [chamber, district] = seat.split("|");
  const rows = prep(
      `SELECT year, candidate, party, votes, total_cast FROM election_history
       WHERE chamber = ? AND district = ? ORDER BY year DESC, votes DESC`,
    )
    .all(chamber, Number(district)) as {
    year: number; candidate: string; party: string | null;
    votes: number; total_cast: number | null;
  }[];
  const byYear = new Map<number, typeof rows>();
  for (const r of rows) {
    if (!byYear.has(r.year)) byYear.set(r.year, []);
    byYear.get(r.year)!.push(r);
  }
  return [...byYear.entries()].map(([year, candidates]) => {
    const total = candidates[0].total_cast ?? candidates.reduce((s, c) => s + c.votes, 0);
    return { year, total, candidates };
  });
});

/** The seat's most recent general-election margin, for competitiveness
 * context: percentage-point gap between the top two candidates over the
 * official ballots cast, or null margin when unopposed. */
export const lastMarginFor = (chamber: string | null, district: number | null) => {
  const history = electionHistoryFor(chamber, district);
  if (!history.length) return null;
  const { year, total, candidates } = history[0];
  if (candidates.length < 2) return { year, margin: null };
  const gap = candidates[0].votes - candidates[1].votes;
  return { year, margin: total > 0 ? (gap / total) * 100 : null };
};

/** Certified county aggregates for one statewide contest, alphabetical,
 * candidates ordered by statewide finish within each county. */
export const statewideCountiesFor = (office: string) =>
  prep(
      `SELECT year, county, candidate, party, votes FROM statewide_county_results
       WHERE office = ? ORDER BY year DESC, county, votes DESC`,
    )
    .all(office) as {
    year: number; county: string; candidate: string;
    party: string | null; votes: number;
  }[];

// donors report occupations in arbitrary casing; de-shout long all-caps
// words but keep short ones (CEO, RN, CPA) as likely acronyms
const deShout = (s: string): string => {
  const trimmed = s.trim();
  return /^not employed$/i.test(trimmed)
    ? "Not employed"
    : trimmed
        .split(/\s+/)
        .map((w) => (w.length > 3 && w === w.toUpperCase() ? w[0] + w.slice(1).toLowerCase() : w))
        .join(" ");
};

/** "While in office" means inside a recorded service term. Terms come
 * from the people files and end mid-biennium on recalls and
 * resignations; out-of-office gaps never count for or against anyone.
 * This rule is written exactly once. */
export const termsFor = (personId: string) =>
  prep(
      "SELECT chamber, district, start, end, end_label, end_url FROM person_terms"
      + " WHERE person_id = ? ORDER BY start",
    )
    .all(personId) as {
      chamber: string; district: number | null; start: string; end: string | null;
      end_label: string | null; end_url: string | null;
    }[];

const officeEntryFor = (personId: string): string => {
  const terms = termsFor(personId);
  return terms.length ? terms[0].start : OPEN_END;
};

// windows every contribution row to a service term of its recipient;
// EXISTS so overlapping term records can never double-count a receipt
const IN_TERM = `EXISTS (
  SELECT 1 FROM person_terms t
  WHERE t.person_id = c.person_id
  AND c.date >= t.start AND c.date <= COALESCE(t.end, '${OPEN_END}')
)`;
const WINDOWED = `(
  SELECT c.* FROM contributions c
  WHERE ${IN_TERM} AND c.date >= @start AND c.date <= @end
) c`;
const NO_BOUNDS = { start: OPEN_START, end: OPEN_END };

const windowedAll = <T>(sql: string, extra: Record<string, unknown> = {}): T[] =>
  prep(sql).all({ ...NO_BOUNDS, ...extra }) as T[];
const windowedGet = <T>(sql: string, extra: Record<string, unknown> = {}): T =>
  prep(sql).get({ ...NO_BOUNDS, ...extra }) as T;

/** Campaign money summary for one legislator, windowed to their time in
 * office. Three honest states: null = no committee mapped (say "not
 * linked", never "$0"); {total: 0} = mapped but no receipts; else data. */
export const moneyFor = (personId: string) => {
  // a mapping with zero receipts across all recorded history means the
  // member's active committee isn't linked yet (surname-only committee
  // names never auto-match); show the coverage gap, never a false $0
  const mapped = prep("SELECT COUNT(*) AS n FROM contributions WHERE person_id = ?")
    .get(personId) as { n: number };
  if (mapped.n === 0) return null;
  const entry = officeEntryFor(personId);
  const P = { person: personId };
  const summary = prep(
      `SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total,
              COALESCE(SUM(CASE WHEN from_type = 'Individual' THEN amount ELSE 0 END), 0)
                AS individualTotal,
              MIN(date) AS first, MAX(date) AS last
       FROM contributions c WHERE c.person_id = @person AND ${IN_TERM}`,
    )
    .get(P) as {
      n: number; total: number; individualTotal: number;
      first: string | null; last: string | null;
    };
  // committee donors grouped by CFIS entity id (collision-proof), never name
  const committees = prep(
      `SELECT from_entity_id AS entityId, MAX(from_name) AS name,
              SUM(amount) AS total, COUNT(*) AS n
       FROM contributions c
       WHERE c.person_id = @person AND ${IN_TERM}
       AND from_type = 'Registrant' AND from_entity_id IS NOT NULL
       GROUP BY from_entity_id ORDER BY total DESC LIMIT 5`,
    )
    .all(P) as { entityId: number; name: string; total: number; n: number }[];
  const occupations = prep(
      `SELECT occupation, SUM(amount) AS total, COUNT(*) AS n
       FROM contributions c
       WHERE c.person_id = @person AND ${IN_TERM} AND from_type = 'Individual'
       AND occupation IS NOT NULL AND TRIM(occupation) != ''
       GROUP BY LOWER(TRIM(occupation)) ORDER BY total DESC LIMIT 5`,
    )
    .all(P) as { occupation: string; total: number; n: number }[];
  for (const o of occupations) o.occupation = deShout(o.occupation);
  const quarters = prep(
      `SELECT substr(date, 1, 4) || '-Q' ||
              ((CAST(substr(date, 6, 2) AS INTEGER) + 2) / 3) AS q,
              SUM(amount) AS total
       FROM contributions c
       WHERE c.person_id = @person AND ${IN_TERM} AND date != ''
       GROUP BY q ORDER BY q`,
    )
    .all(P) as { q: string; total: number }[];
  // composition by CFIS source type, exactly as the committee reported it
  const byType = prep(
      `SELECT COALESCE(from_type, 'Other') AS type, SUM(amount) AS total, COUNT(*) AS n
       FROM contributions c WHERE c.person_id = @person AND ${IN_TERM}
       GROUP BY COALESCE(from_type, 'Other') ORDER BY total DESC`,
    )
    .all(P) as { type: string; total: number; n: number }[];
  // individual donors grouped by CFIS entity id (collision-proof), never name
  const individuals = prep(
      `SELECT from_entity_id AS entityId, MAX(from_name) AS name,
              SUM(amount) AS total, COUNT(*) AS n
       FROM contributions c
       WHERE c.person_id = @person AND ${IN_TERM}
       AND from_type = 'Individual' AND from_entity_id IS NOT NULL
       GROUP BY from_entity_id ORDER BY total DESC LIMIT 5`,
    )
    .all(P) as { entityId: number; name: string; total: number; n: number }[];
  return { ...summary, entry, committees, occupations, quarters, byType, individuals };
};

interface CommitteeAgg {
  entityId: number; name: string; total: number; n: number;
  recipients: number; first: string; last: string;
}
// one committee aggregate serves the dollar ranking, the breadth
// ranking, and the donor pages; callers sort and slice
const COMMITTEE_AGG = `
  SELECT c.from_entity_id AS entityId, MAX(c.from_name) AS name,
         SUM(c.amount) AS total, COUNT(*) AS n,
         COUNT(DISTINCT c.person_id) AS recipients,
         MIN(c.date) AS first, MAX(c.date) AS last
  FROM ${WINDOWED}
  WHERE c.from_type = 'Registrant' AND c.from_entity_id IS NOT NULL
  GROUP BY c.from_entity_id`;

const partyTotals = (where: string, extra: Record<string, unknown> = {}) =>
  windowedAll<{ party: string | null; total: number; legislators: number }>(
    `SELECT p.party, COALESCE(SUM(c.amount), 0) AS total,
            COUNT(DISTINCT c.person_id) AS legislators
     FROM ${WINDOWED} JOIN people p ON p.id = c.person_id ${where}
     GROUP BY p.party ORDER BY total DESC`,
    extra,
  );

// covered = members whose linked committees actually carry receipts; a
// receipt-less mapping is an incomplete link, not coverage
const coverage = once(() => ({
  covered: (prep("SELECT COUNT(DISTINCT person_id) AS n FROM contributions").get() as { n: number }).n,
  sitting: (prep("SELECT COUNT(*) AS n FROM people WHERE current_role IN ('Representative', 'Senator')")
    .get() as { n: number }).n,
}));

/** Statewide rollup of the same contribution data shown on profiles,
 * each member's receipts windowed to their time in office, optionally
 * intersected with an election-cycle date range. Covers only
 * legislators with a linked committee; rankings compare within that
 * covered set, never beyond it. */
export const moneyOverview = (bounds: Record<string, string> = {}) => {
  const summary = windowedGet<{
    n: number; total: number; first: string | null; last: string | null;
  }>(
    `SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total,
            MIN(c.date) AS first, MAX(c.date) AS last
     FROM ${WINDOWED}`,
    bounds,
  );
  const individuals = windowedGet<{ t: number; small: number }>(
    `SELECT COALESCE(SUM(amount), 0) AS t,
            COALESCE(SUM(CASE WHEN amount < 200 THEN amount ELSE 0 END), 0) AS small
     FROM ${WINDOWED} WHERE c.from_type = 'Individual'`,
    bounds,
  );
  const committeeTotal = windowedGet<{ t: number }>(
    `SELECT COALESCE(SUM(amount), 0) AS t FROM ${WINDOWED}
     WHERE c.from_type = 'Registrant'`,
    bounds,
  ).t;
  const agg = Object.keys(bounds).length
    ? windowedAll<CommitteeAgg>(COMMITTEE_AGG, bounds)
    : committeeAggAll();
  const topCommittees = [...agg].sort((a, b) => b.total - a.total).slice(0, 20);
  const widestCommittees = [...agg]
    .sort((a, b) => b.recipients - a.recipients || b.total - a.total)
    .slice(0, 20);
  const topLegislators = windowedAll<{
    id: string; name: string; party: string | null; chamber: string | null;
    district: number | null; total: number; n: number;
  }>(
    `SELECT c.person_id AS id, p.name, p.party, p.chamber, p.district,
            SUM(c.amount) AS total, COUNT(*) AS n
     FROM ${WINDOWED} JOIN people p ON p.id = c.person_id
     GROUP BY c.person_id ORDER BY total DESC LIMIT 20`,
    bounds,
  );
  const topOccupations = windowedAll<{ occupation: string; total: number; n: number }>(
    `SELECT c.occupation AS occupation, SUM(c.amount) AS total, COUNT(*) AS n
     FROM ${WINDOWED}
     WHERE c.from_type = 'Individual'
     AND c.occupation IS NOT NULL AND TRIM(c.occupation) != ''
     GROUP BY LOWER(TRIM(c.occupation)) ORDER BY total DESC LIMIT 10`,
    bounds,
  );
  for (const o of topOccupations) o.occupation = deShout(o.occupation);
  return {
    ...summary, ...coverage(),
    individualTotal: individuals.t, smallDollarTotal: individuals.small,
    committeeTotal,
    topCommittees, widestCommittees, topLegislators,
    byParty: partyTotals("", bounds), topOccupations,
  };
};

// the lifetime (no-bounds) aggregate is shared by the money overview's
// Lifetime view and the donor-page set; callers never mutate it in place
const committeeAggAll = once(() => windowedAll<CommitteeAgg>(COMMITTEE_AGG));

/** Committee donors that get their own page: at least $1,000 given to
 * sitting legislators while in office. */
export const donorCommittees = once(() =>
  committeeAggAll()
    .filter((c) => c.total >= 1000)
    .sort((a, b) => b.total - a.total),
);

const donorIds = once(() => new Set(donorCommittees().map((c) => c.entityId)));
export const hasDonorPage = (entityId: number | null): boolean =>
  entityId != null && donorIds().has(entityId);

/** One committee donor's giving to sitting legislators, in-office windowed. */
export const donorCommitteeFor = (entityId: number) => ({
  recipients: windowedAll<{
    id: string; name: string; party: string | null; chamber: string | null;
    district: number | null; total: number; n: number; first: string; last: string;
  }>(
    `SELECT c.person_id AS id, p.name, p.party, p.chamber, p.district,
            SUM(c.amount) AS total, COUNT(*) AS n,
            MIN(c.date) AS first, MAX(c.date) AS last
     FROM ${WINDOWED} JOIN people p ON p.id = c.person_id
     WHERE c.from_entity_id = @entityId
     GROUP BY c.person_id ORDER BY total DESC`,
    { entityId },
  ),
  byParty: partyTotals("WHERE c.from_entity_id = @entityId", { entityId }),
});

/** Committees for the directory and each committee's own page: membership,
 * throughput, and the next scheduled hearing when one exists. Two counted
 * figures, neither inferred: hearings held (joined on committee_id) and
 * bills that died here without ever getting one.
 *
 * The second matches on name *and* chamber. The importer records both
 * (`committee_at_death`, `committee_chamber_at_death`) precisely so a
 * same-named committee in the other house is never blamed, and every one
 * of the 9,465 graveyard bills carries a chamber. Matching on name alone
 * gave Assembly and Senate Education the same 567 bills. One query feeds
 * the directory and the page, so the two can never disagree. */
export const allCommittees = once(() =>
  prep(
      `SELECT c.id, c.name, c.chamber, c.chair_person_id, p.name AS chair_name,
              COUNT(m.person_id) AS member_count,
              (SELECT COUNT(*) FROM hearings h WHERE h.committee_id = c.id) AS hearings_held,
              (SELECT MIN(h.date) FROM hearings h
                WHERE h.committee_id = c.id AND h.date >= date('now')) AS next_hearing,
              (SELECT COUNT(*) FROM bills b
                WHERE b.died_without_hearing = 1 AND b.source != 'legiscan'
                AND b.committee_at_death = c.name
                AND COALESCE(b.committee_chamber_at_death, '') = COALESCE(c.chamber, '')
              ) AS died_here
       FROM committees c
       LEFT JOIN committee_members m ON m.committee_id = c.id
       LEFT JOIN people p ON p.id = c.chair_person_id
       GROUP BY c.id HAVING member_count > 0 ORDER BY c.name`,
    )
    .all() as {
      id: string; name: string; chamber: string | null;
      chair_person_id: string | null; chair_name: string | null; member_count: number;
      hearings_held: number; next_hearing: string | null; died_here: number;
    }[],
);

// mirror of importer/committees.py normalize_name, for matching the
// graveyard's committee_at_death names to committee pages
const normalizeCommitteeName = (name: string): string => {
  let key = name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  for (;;) {
    const stripped = key.replace(/^(joint |committee on )/, "");
    if (stripped === key) return key;
    key = stripped;
  }
};

// the graveyard aggregate takes no parameters: one scan (with each
// referral's normalized key precomputed) serves every committee page
const graveyardAgg = once(() =>
  (
    prep(
      `SELECT session_id, committee_at_death,
              committee_chamber_at_death AS chamber, COUNT(*) AS n
       FROM bills WHERE died_without_hearing = 1 AND committee_at_death IS NOT NULL
       GROUP BY session_id, committee_at_death, chamber
       ORDER BY session_id DESC`,
    ).all() as {
      session_id: string; committee_at_death: string;
      chamber: string | null; n: number;
    }[]
  ).map((g) => ({
    ...g,
    key: normalizeCommitteeName(g.committee_at_death),
    referralIsJoint: /^joint\b/i.test(g.committee_at_death),
  })),
);

/** One committee: members, hearings, and its Hearing None record.
 * Graveyard rows attach only on exact normalized-name + chamber match. */
export const committeeFor = (committeeId: string) => {
  const members = prep(
      `SELECT m.person_id AS id, m.role, p.name, p.party, p.chamber, p.district,
              p.current_role
       FROM committee_members m JOIN people p ON p.id = m.person_id
       WHERE m.committee_id = ?
       ORDER BY ${ROLE_ORDER}, p.name`,
    )
    .all(committeeId) as {
      id: string; role: string; name: string; party: string | null;
      chamber: string | null; district: number | null; current_role: string | null;
    }[];
  const committee = prep("SELECT id, name, chamber FROM committees WHERE id = ?")
    .get(committeeId) as { id: string; name: string; chamber: string | null };
  const hearings = prep(`${HEARING_SELECT} WHERE h.committee_id = ? ORDER BY h.date DESC LIMIT 15`)
    .all(committeeId) as Hearing[];
  const key = normalizeCommitteeName(committee.name);
  // chamber committees require the referral's chamber to match; joint
  // committees require the referral text to say Joint. Same-named
  // committees in different chambers can never merge.
  const graveyard = graveyardAgg()
    .filter((g) => {
      if (g.key !== key) return false;
      if (committee.chamber == null) return g.referralIsJoint;
      return !g.referralIsJoint && g.chamber === committee.chamber;
    })
    .map(({ key: _k, referralIsJoint: _j, ...row }) => row);
  return { committee, members, hearings, graveyard };
};

/** The state's subject index, aggregated. */
export const allSubjects = () =>
  prep(
      `SELECT subject, COUNT(*) AS n FROM bill_subjects
       GROUP BY subject ORDER BY subject`,
    )
    .all() as { subject: string; n: number }[];

export const billsForSubject = (subject: string) =>
  prep(
      `SELECT b.id, b.session_id, b.identifier, b.title, b.status,
              b.died_without_hearing, b.latest_action_date
       FROM bill_subjects s JOIN bills b ON b.id = s.bill_id
       WHERE s.subject = ? AND b.source != 'legiscan'
       ORDER BY b.session_id DESC, LENGTH(b.identifier), b.identifier`,
    )
    .all(subject) as {
      id: string; session_id: string; identifier: string;
      title: string | null; status: string | null;
      died_without_hearing: number; latest_action_date: string | null;
    }[];

export const subjectsForBill = (billId: string) =>
  prep("SELECT subject FROM bill_subjects WHERE bill_id = ? ORDER BY subject")
    .all(billId) as { subject: string }[];

/** Official documents attached to a bill; note text is docs.legis's own,
 * displayed verbatim. */
export const documentsFor = (billId: string) =>
  prep("SELECT note, url FROM bill_documents WHERE bill_id = ? ORDER BY note")
    .all(billId) as { note: string; url: string }[];

/** Organizations registered as lobbying on a bill (an interest
 * registration, not a for/against position). */
export const lobbyingFor = (billId: string) =>
  prep(
      `SELECT principal_id, principal, source_url FROM lobbying_interests
       WHERE bill_id = ? ORDER BY principal`,
    )
    .all(billId) as { principal_id: number; principal: string; source_url: string | null }[];

/** ---- New laws, veto tracker, key votes ---- */

const bienniumOf = (sessionId: string): number => {
  const y = Number(sessionId.slice(0, 4));
  return y % 2 ? y : y - 1;
};

const ACT_RE = /Wisconsin Act (\d+)/i;
// the approval action prints M-D-YYYY; stored as ISO like every other date
const APPROVED_RE = /on (\d{1,2})-(\d{1,2})-(\d{4})/;
const approvedIso = (description: string): string | null => {
  const m = APPROVED_RE.exec(description);
  return m ? `${m[3]}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}` : null;
};
// matches every passage-stage motion phrasing on floor roll calls,
// including the terse all-caps docs ('PASSAGE', 'CONCURRENCE AS AMENDED');
// the negative guard keeps procedural motions that merely mention passage
// (refused to reconsider the vote by which the bill passed) out
const PASSAGE_RE = /read a third time|concurred in|passed|passage|concurrence/i;
const NOT_PASSAGE_RE = /refused|reconsider|nonconcur|reject|laid on table|suspend/i;
const isPassage = (motion: string | null): boolean =>
  motion != null && PASSAGE_RE.test(motion) && !NOT_PASSAGE_RE.test(motion);

export interface LawVote {
  id: string; chamber: string | null; motion: string | null;
  yes: number; no: number; date: string | null;
}
export interface Law {
  bill_id: string; session_id: string; identifier: string; title: string | null;
  act: number; approved: string | null; partial: boolean; votes: LawVote[];
}

/** Each chamber's last recorded passage roll call on one bill. Voice and
 * paper votes leave no roll-call document and are omitted, never guessed. */
const passageVotes = (billId: string): LawVote[] => {
  const events = prep(
      `SELECT id, chamber, motion, yes_count, no_count, date FROM vote_events
       WHERE bill_id = ? AND source_url LIKE '%/votes/%'
       AND COALESCE(yes_count, 0) + COALESCE(no_count, 0) > 0
       ORDER BY date, id`,
    )
    .all(billId) as {
      id: string; chamber: string | null; motion: string | null;
      yes_count: number; no_count: number; date: string | null;
    }[];
  const last = new Map<string, LawVote>();
  for (const e of events) {
    if (!e.chamber || !isPassage(e.motion)) continue;
    last.set(e.chamber, {
      id: e.id, chamber: e.chamber, motion: e.motion,
      yes: e.yes_count, no: e.no_count, date: e.date,
    });
  }
  return ["upper", "lower"].flatMap((c) => (last.has(c) ? [last.get(c)!] : []));
};

/** Every act of law from one biennium, in act-number order. The act
 * number and approval date come verbatim from the governor's approval
 * action in the official bill history. */
export const lawsFor = memoBy((biennium: number): Law[] => {
  const rows = prep(
      `SELECT b.id, b.session_id, b.identifier, b.title, a.description
       FROM bills b JOIN actions a ON a.bill_id = b.id
       WHERE b.status = 'enacted' AND b.source != 'legiscan'
       AND CAST(substr(b.session_id, 1, 4) AS INTEGER) IN (?, ?)
       AND a.description LIKE '%Wisconsin Act %'`,
    )
    .all(biennium, biennium + 1) as {
      id: string; session_id: string; identifier: string;
      title: string | null; description: string;
    }[];
  const laws = rows
    .map((r) => ({
      bill_id: r.id, session_id: r.session_id, identifier: r.identifier,
      title: r.title,
      act: Number(ACT_RE.exec(r.description)![1]),
      approved: approvedIso(r.description),
      partial: /partial veto/i.test(r.description),
      votes: passageVotes(r.id),
    }))
    .sort((a, b) => a.act - b.act);
  return laws;
});

/** Bienniums covered by this build that produced acts, newest first. */
export const lawBienniums = () =>
  [...new Set(builtSessions().map((s) => bienniumOf(s.id)))]
    .sort((a, b) => b - a)
    .map((biennium) => ({ biennium, laws: lawsFor(biennium) }))
    .filter((b) => b.laws.length > 0);

/** The governor's official veto message for a bill, when docs.legis
 * attaches one. */
export const vetoMessageUrl = (billId: string): string | null =>
  (prep(
      "SELECT url FROM bill_documents WHERE bill_id = ? AND note = 'Veto Message'",
    ).get(billId) as { url: string } | undefined)?.url ?? null;

export interface VetoBiennium {
  biennium: number;
  fullVetoes: {
    bill_id: string; session_id: string; identifier: string;
    title: string | null; date: string | null;
  }[];
  partialVetoes: Law[];
  attempts: {
    bill_id: string; session_id: string; identifier: string; title: string | null;
    date: string; description: string; vote: LawVote | null;
  }[];
}

/** Vetoes and override attempts per built biennium, straight from the
 * official history: full vetoes (bill status), partial vetoes (approval
 * text), and every "notwithstanding the objections" attempt with its
 * roll call where one was recorded. */
export const vetoTracker = (): VetoBiennium[] =>
  [...new Set(builtSessions().map((s) => bienniumOf(s.id)))]
    .sort((a, b) => b - a)
    .map((biennium) => {
      const years = [biennium, biennium + 1];
      const fullVetoes = (prep(
          `SELECT b.id AS bill_id, b.session_id, b.identifier, b.title, a.date
           FROM bills b LEFT JOIN actions a ON a.bill_id = b.id
             AND LOWER(a.description) LIKE '%vetoed by the governor%'
           WHERE b.status = 'vetoed' AND b.source != 'legiscan'
           AND CAST(substr(b.session_id, 1, 4) AS INTEGER) IN (?, ?)
           GROUP BY b.id ORDER BY MAX(a.date) DESC, b.id`,
        )
        .all(...years)) as VetoBiennium["fullVetoes"];
      const partialVetoes = lawsFor(biennium).filter((l) => l.partial);
      const attemptRows = prep(
          `SELECT b.id AS bill_id, b.session_id, b.identifier, b.title,
                  a.date, a.description
           FROM actions a JOIN bills b ON b.id = a.bill_id
           WHERE LOWER(a.description) LIKE '%notwithstanding the objections%'
           AND b.source != 'legiscan'
           AND CAST(substr(b.session_id, 1, 4) AS INTEGER) IN (?, ?)
           ORDER BY a.date DESC, b.id`,
        )
        .all(...years) as {
          bill_id: string; session_id: string; identifier: string;
          title: string | null; date: string; description: string;
        }[];
      const attempts = attemptRows.map((a) => {
        const vote = prep(
            `SELECT id, chamber, motion, yes_count AS yes, no_count AS no, date
             FROM vote_events WHERE bill_id = ? AND substr(date, 1, 10) = ?
             AND LOWER(motion) LIKE '%notwithstanding%'
             AND source_url LIKE '%/votes/%' LIMIT 1`,
          )
          .get(a.bill_id, a.date.slice(0, 10)) as LawVote | undefined;
        return { ...a, vote: vote ?? null };
      });
      return { biennium, fullVetoes, partialVetoes, attempts };
    })
    .filter((b) => b.fullVetoes.length || b.partialVetoes.length || b.attempts.length);

/** Roll calls that qualify as key votes, by rule: the final recorded
 * passage vote of every bill that became law, any floor vote decided by
 * five or fewer, and every veto-override vote. One scan serves every
 * legislator page. */
const keyEvents = once((): Map<string, string[]> => {
  const m = new Map<string, string[]>();
  const add = (id: string, kind: string) => {
    const kinds = m.get(id) ?? [];
    if (!kinds.includes(kind)) kinds.push(kind);
    m.set(id, kinds);
  };
  const lawEvents = prep(
      `SELECT e.id, e.bill_id, e.chamber, e.motion FROM vote_events e
       JOIN bills b ON b.id = e.bill_id
       WHERE b.status = 'enacted' AND e.source_url LIKE '%/votes/%'
       AND COALESCE(e.yes_count, 0) + COALESCE(e.no_count, 0) > 0
       ORDER BY e.date, e.id`,
    )
    .all() as { id: string; bill_id: string; chamber: string | null; motion: string | null }[];
  const lastPassage = new Map<string, string>();
  for (const e of lawEvents) {
    if (e.chamber && isPassage(e.motion)) {
      lastPassage.set(`${e.bill_id}|${e.chamber}`, e.id);
    }
  }
  for (const id of lastPassage.values()) add(id, "became law");
  for (const { id } of prep(
      `SELECT id FROM vote_events WHERE source_url LIKE '%/votes/%'
       AND COALESCE(yes_count, 0) + COALESCE(no_count, 0) > 0
       AND ABS(yes_count - no_count) <= 5`,
    ).all() as { id: string }[]) {
    add(id, "close vote");
  }
  for (const { id } of prep(
      `SELECT id FROM vote_events WHERE source_url LIKE '%/votes/%'
       AND LOWER(motion) LIKE '%notwithstanding%'`,
    ).all() as { id: string }[]) {
    add(id, "veto override");
  }
  return m;
});

/** One member's votes on the key roll calls, newest first. */
export const keyVotesFor = (personId: string) => {
  const keys = keyEvents();
  const rows = prep(
      `SELECT r.option, e.id AS vote_event_id, e.date, e.motion,
              e.yes_count, e.no_count,
              b.identifier, b.title, b.session_id
       FROM vote_records r
       JOIN vote_events e ON e.id = r.vote_event_id
       JOIN bills b ON b.id = e.bill_id
       WHERE r.person_id = ? ORDER BY e.date DESC, e.id`,
    )
    .all(personId) as {
      option: string; vote_event_id: string; date: string | null;
      motion: string | null; yes_count: number | null; no_count: number | null;
      identifier: string; title: string | null; session_id: string;
    }[];
  return rows
    .filter((r) => keys.has(r.vote_event_id))
    .map((r) => ({ ...r, kinds: keys.get(r.vote_event_id)! }));
};

/** ---- Committee money: PACs, conduits, parties, independent expenditures ---- */

export interface CfCommittee {
  entity_id: number;
  name: string;
  committee_type: string | null;
  assigned_id: string | null;
}

/** entity id -> registration type, so a PAC, a party transfer and a
 * conduit pass-through are never shown as the same kind of donor. */
const cfCommittees = once(
  (): Map<number, CfCommittee> =>
    new Map(
      (prep("SELECT * FROM cf_committees").all() as CfCommittee[]).map((c) => [c.entity_id, c]),
    ),
);

export const cfTypeOf = (entityId: number | null): string | null =>
  entityId == null ? null : cfCommittees().get(entityId)?.committee_type ?? null;

/** One committee's money: totals, top donors, top recipients. */
export const cfCommitteeFor = (entityId: number) => {
  const committee = prep("SELECT * FROM cf_committees WHERE entity_id = ?")
    .get(entityId) as CfCommittee | undefined;
  if (!committee) return null;
  // We collect a candidate committee's receipts through the verified
  // legislator map, not this table, so its rows here are only the stray
  // stanced ones. Totalling those would present a fraction of the
  // committee's money as all of it.
  if (committee.committee_type === "State Candidate"
      || committee.committee_type === "Federal Candidate") {
    return null;
  }
  const totals = prep(
      `SELECT COALESCE(SUM(CASE WHEN direction = 'INCOMING' THEN amount END), 0) AS raised,
              COALESCE(SUM(CASE WHEN direction = 'OUTGOING' THEN amount END), 0) AS spent,
              COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last
       FROM cf_transactions WHERE filer_entity_id = ?`,
    ).get(entityId) as {
      raised: number; spent: number; n: number; first: string | null; last: string | null;
    };
  const side = (direction: "INCOMING" | "OUTGOING") =>
    prep(
        `SELECT other_entity_id AS entityId, MAX(other_name) AS name,
                MAX(other_type) AS type, SUM(amount) AS total, COUNT(*) AS n
         FROM cf_transactions
         WHERE filer_entity_id = ? AND direction = ? AND other_name IS NOT NULL
         GROUP BY COALESCE(other_entity_id, other_name)
         ORDER BY total DESC LIMIT 50`,
      )
      .all(entityId, direction) as {
        entityId: number | null; name: string; type: string | null;
        total: number; n: number;
      }[];
  return {
    committee,
    ...totals,
    donors: side("INCOMING"),
    payees: side("OUTGOING"),
    advocacy: prep(
        `SELECT date, amount, stance, related_name, related_office, related_district, purpose
         FROM cf_transactions WHERE filer_entity_id = ? AND stance IS NOT NULL
         AND related_name IS NOT NULL
         ORDER BY date DESC LIMIT 100`,
      ).all(entityId) as {
        date: string; amount: number; stance: string; related_name: string | null;
        related_office: string | null; related_district: string | null; purpose: string | null;
      }[],
  };
};

/** Express advocacy: money spent for or against candidates by someone
 * other than the candidate. It never appears in a candidate's own
 * filings, which is exactly why it is worth surfacing separately.
 * Candidate committees also file stanced rows for their own ads; those
 * are the candidate's own spending, not third-party advocacy, and are
 * excluded here so the two are never conflated. */
export const independentExpenditures = (limit = 500) =>
  prep(
      `SELECT t.id, t.date, t.amount, t.stance, t.related_name, t.related_office,
              t.related_district, t.purpose, t.other_name, t.filer_entity_id,
              t.report_id, t.report_name,
              c.name AS filer_name, c.committee_type AS filer_type
       FROM cf_transactions t
       LEFT JOIN cf_committees c ON c.entity_id = t.filer_entity_id
       WHERE t.stance IS NOT NULL AND t.related_name IS NOT NULL
       AND COALESCE(t.filer_type, '') NOT IN ('State Candidate', 'Federal Candidate')
       ORDER BY t.date DESC, t.amount DESC LIMIT ?`,
    )
    .all(limit) as {
      id: number; date: string; amount: number; stance: string; related_name: string | null;
      related_office: string | null; related_district: string | null;
      purpose: string | null; other_name: string | null; filer_entity_id: number;
      report_id: number | null; report_name: string | null;
      filer_name: string | null; filer_type: string | null;
    }[];

/** Conduits pass earmarked individual money through to a candidate; the
 * conduit is the filer, but the money is not the conduit's own. */
export const conduitFlows = (limit = 200) =>
  prep(
      `SELECT c.name AS conduit, t.final_recipient_name AS recipient,
              SUM(t.amount) AS total, COUNT(*) AS n
       FROM cf_transactions t JOIN cf_committees c ON c.entity_id = t.filer_entity_id
       WHERE t.final_recipient_name IS NOT NULL
       GROUP BY c.name, t.final_recipient_name
       ORDER BY total DESC LIMIT ?`,
    )
    .all(limit) as { conduit: string; recipient: string; total: number; n: number }[];

export const sessionStats = (sessionId: string) =>
  prep(
      `SELECT COUNT(*) AS bills,
              SUM(CASE WHEN status = 'enacted' THEN 1 ELSE 0 END) AS enacted,
              SUM(CASE WHEN status = 'vetoed' THEN 1 ELSE 0 END) AS vetoed,
              SUM(died_without_hearing) AS graveyard
       FROM bills WHERE session_id = ?`,
    )
    .get(sessionId) as { bills: number; enacted: number; vetoed: number; graveyard: number };

/** What became of a session's bills, as a flow that balances.
 *
 * Bills only. Joint and simple resolutions are counted separately, because
 * they never reach the governor and cannot become law: a joint resolution
 * needs both chambers, a simple one needs only its own, and folding all
 * three together is what made the old cumulative funnel's middle stage
 * mean two different things at once.
 *
 * Every bill lands in exactly one terminal bucket, so the branches sum to
 * the total at each split and the diagram cannot quietly lose any. Nothing
 * is modelled: `died` is the explicit "failed pursuant to Senate Joint
 * Resolution 1" status recorded in the official history, not an inference
 * drawn from silence, and anything neither finished nor explicitly failed
 * is counted as still moving rather than called dead.
 */
export const sessionBillFlow = (sessionId: string) => {
  const r = prep(
      `SELECT COUNT(*) AS introduced,
              SUM(CASE WHEN status = 'enacted' THEN 1 ELSE 0 END) AS enacted,
              SUM(CASE WHEN status = 'vetoed' THEN 1 ELSE 0 END) AS vetoed,
              SUM(CASE WHEN status = 'failed_sjr1' THEN 1 ELSE 0 END) AS died,
              SUM(CASE WHEN status = 'failed_sjr1' AND died_without_hearing = 1
                       THEN 1 ELSE 0 END) AS noHearing
       FROM bills
       WHERE session_id = ? AND source != 'legiscan' AND classification = 'bill'`,
    )
    .get(sessionId) as {
    introduced: number; enacted: number; vetoed: number;
    died: number; noHearing: number;
  };
  const resolutions = (
    prep(
      `SELECT COUNT(*) AS n FROM bills
       WHERE session_id = ? AND source != 'legiscan' AND classification != 'bill'`,
    ).get(sessionId) as { n: number }
  ).n;
  const passedBoth = r.enacted + r.vetoed;
  return {
    ...r,
    passedBoth,
    heard: r.died - r.noHearing,
    moving: r.introduced - passedBoth - r.died,
    resolutions,
  };
};

