/** Build-time SQLite access. Runs only during `astro build` — never in the
 * browser. BUILD_SESSIONS (comma-separated session ids) limits which
 * sessions render; default is the current biennium. `all` renders history
 * (Phase 6 merges a prebuilt historical artifact instead). */
import Database from "better-sqlite3";
import { fileURLToPath } from "node:url";

const DB_PATH = fileURLToPath(new URL("../../../data/wi.sqlite", import.meta.url));
const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });

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
}

export const allSessions = (): Session[] =>
  db.prepare("SELECT * FROM sessions ORDER BY id DESC").all() as Session[];

export function builtSessions(): Session[] {
  const env = process.env.BUILD_SESSIONS ?? "2025,2026s1";
  const sessions = allSessions();
  if (env === "all") return sessions;
  const wanted = new Set(env.split(",").map((s) => s.trim()));
  return sessions.filter((s) => wanted.has(s.id));
}

export const meta = (): Record<string, string> =>
  Object.fromEntries(
    (db.prepare("SELECT key, value FROM meta").all() as { key: string; value: string }[]).map(
      (r) => [r.key, r.value],
    ),
  );

export const billsFor = (sessionId: string): Bill[] =>
  db
    .prepare("SELECT * FROM bills WHERE session_id = ? AND source != 'legiscan' ORDER BY id")
    .all(sessionId) as Bill[];

export const actionsFor = (billId: string) =>
  db
    .prepare(
      "SELECT date, chamber, description, classification FROM actions WHERE bill_id = ? ORDER BY date, id",
    )
    .all(billId) as { date: string; chamber: string | null; description: string; classification: string }[];

export const sponsorsFor = (billId: string) =>
  db
    .prepare(
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
  db
    .prepare("SELECT * FROM vote_events WHERE bill_id = ? ORDER BY date, id")
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
  db
    .prepare(
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
  db.prepare("SELECT * FROM people ORDER BY name").all() as Person[];

export const sittingPeople = (): Person[] =>
  db
    .prepare(
      "SELECT * FROM people WHERE current_role IN ('Representative', 'Senator') ORDER BY chamber, district",
    )
    .all() as Person[];

export const personVotes = (personId: string, limit: number) =>
  db
    .prepare(
      `SELECT r.option, e.id AS vote_event_id, e.date, e.motion, e.result,
              b.id AS bill_id, b.identifier, b.title, b.session_id
       FROM vote_records r
       JOIN vote_events e ON e.id = r.vote_event_id
       JOIN bills b ON b.id = e.bill_id
       WHERE r.person_id = ? ORDER BY e.date DESC, e.id LIMIT ?`,
    )
    .all(personId, limit) as {
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

export const personSponsorships = (personId: string) =>
  db
    .prepare(
      `SELECT s.is_primary, b.id AS bill_id, b.identifier, b.title, b.status, b.session_id
       FROM sponsorships s JOIN bills b ON b.id = s.bill_id
       WHERE s.person_id = ? AND b.source != 'legiscan' ORDER BY b.id DESC`,
    )
    .all(personId) as {
    is_primary: number;
    bill_id: string;
    identifier: string;
    title: string | null;
    status: string | null;
    session_id: string;
  }[];

export const electionFor = (personId: string) => {
  const row = db
    .prepare("SELECT * FROM elections WHERE person_id = ?")
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
};

export const graveyardFor = (sessionId: string) =>
  db
    .prepare(
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
  db
    .prepare(
      `SELECT id, identifier, title FROM bills
       WHERE session_id = ? AND died_without_hearing = 1
       AND committee_at_death IS ? ORDER BY id`,
    )
    .all(sessionId, committee) as { id: string; identifier: string; title: string | null }[];

const HEARING_SELECT = `SELECT h.*, c.name AS committee_name, c.chamber AS committee_chamber,
       p.name AS chair_name, c.chair_person_id AS chair_person_id
       FROM hearings h LEFT JOIN committees c ON c.id = h.committee_id
       LEFT JOIN people p ON p.id = c.chair_person_id`;

export const upcomingHearings = (since: string) =>
  db
    .prepare(`${HEARING_SELECT} WHERE h.date >= ? ORDER BY h.date, h.time`)
    .all(since) as Hearing[];

export const recentHearings = (limit: number) =>
  db
    .prepare(`${HEARING_SELECT} ORDER BY h.date DESC, h.time DESC LIMIT ?`)
    .all(limit) as Hearing[];

export const allHearings = () =>
  db.prepare(`${HEARING_SELECT} ORDER BY h.date, h.time`).all() as Hearing[];

/** 'AB 656' -> its bill row in the newest built session that has it. */
const _billIdCache = new Map<string, { id: string; session_id: string } | null>();
export const findBillByIdentifier = (identifier: string) => {
  if (_billIdCache.has(identifier)) return _billIdCache.get(identifier);
  let found: { id: string; session_id: string } | null = null;
  for (const session of builtSessions()) {
    const row = db
      .prepare("SELECT id, session_id FROM bills WHERE session_id = ? AND identifier = ?")
      .get(session.id, identifier) as { id: string; session_id: string } | undefined;
    if (row) {
      found = row;
      break;
    }
  }
  _billIdCache.set(identifier, found);
  return found;
};

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
}

/** Exact-name profile resolver: returns a person id only when exactly one
 * person carries the name; ambiguity or no match stays unlinked. */
let _nameToId: Map<string, string | null> | null = null;
export const personIdByName = (name: string | null): string | null => {
  if (!name) return null;
  if (!_nameToId) {
    _nameToId = new Map();
    for (const p of db.prepare("SELECT id, name FROM people").all() as { id: string; name: string }[]) {
      _nameToId.set(p.name, _nameToId.has(p.name) ? null : p.id);
    }
  }
  return _nameToId.get(name) ?? null;
};

export const recentlyActedBills = (sessionIds: string[], limit = 8) =>
  db
    .prepare(
      `SELECT * FROM bills WHERE session_id IN (${sessionIds.map(() => "?").join(",")})
       AND classification = 'bill' ORDER BY latest_action_date DESC LIMIT ?`,
    )
    .all(...sessionIds, limit) as Bill[];

/** Days each chamber held attributed floor votes: (chamber, date) -> count.
 * Memoized — one scan serves every legislator page in the build. */
let _chamberDays: { chamber: string; date: string; n: number }[] | undefined;
export const chamberVoteDays = () =>
  (_chamberDays ??= db
    .prepare(
      `SELECT chamber, date, COUNT(*) AS n FROM vote_events
       WHERE date IS NOT NULL AND chamber IN ('lower', 'upper')
       AND id IN (SELECT DISTINCT vote_event_id FROM vote_records)
       GROUP BY chamber, date`,
    )
    .all() as { chamber: string; date: string; n: number }[]);

/** One person's per-day participation: cast = aye/nay, nv = present-not-voting. */
export const personVoteDays = (personId: string) =>
  db
    .prepare(
      `SELECT e.date, e.chamber,
              SUM(CASE WHEN r.option IN ('yes', 'no') THEN 1 ELSE 0 END) AS cast,
              SUM(CASE WHEN r.option NOT IN ('yes', 'no') THEN 1 ELSE 0 END) AS nv
       FROM vote_records r JOIN vote_events e ON e.id = r.vote_event_id
       WHERE r.person_id = ? AND e.date IS NOT NULL
       GROUP BY e.date, e.chamber`,
    )
    .all(personId) as { date: string; chamber: string; cast: number; nv: number }[];

// majority position (aye/nay) per (vote event, party); ties excluded
let _partyMajority: Map<string, string> | undefined;
const partyMajorities = (): Map<string, string> => {
  if (_partyMajority) return _partyMajority;
  const rows = db
    .prepare(
      `SELECT r.vote_event_id, p.party, r.option, COUNT(*) AS n
       FROM vote_records r JOIN people p ON p.id = r.person_id
       WHERE r.option IN ('yes', 'no') AND p.party IN ('Democratic', 'Republican')
       GROUP BY r.vote_event_id, p.party, r.option`,
    )
    .all() as { vote_event_id: string; party: string; option: string; n: number }[];
  const counts = new Map<string, { yes: number; no: number }>();
  for (const row of rows) {
    const key = `${row.vote_event_id}|${row.party}`;
    const c = counts.get(key) ?? { yes: 0, no: 0 };
    c[row.option as "yes" | "no"] += row.n;
    counts.set(key, c);
  }
  _partyMajority = new Map();
  for (const [key, c] of counts) {
    if (c.yes !== c.no) _partyMajority.set(key, c.yes > c.no ? "yes" : "no");
  }
  return _partyMajority;
};

/** Share of a member's aye/nay floor votes matching their party's majority
 * position, per session. Presented as a plain number, never a grade. */
export const partyAgreement = (personId: string, party: string | null) => {
  if (party !== "Democratic" && party !== "Republican") return [];
  const majorities = partyMajorities();
  const votes = db
    .prepare(
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

/** Official WEC general-election results for one seat, newest first. */
export const electionHistoryFor = (chamber: string | null, district: number | null) => {
  if (!chamber || district == null) return [];
  const rows = db
    .prepare(
      `SELECT year, candidate, party, votes FROM election_history
       WHERE chamber = ? AND district = ? ORDER BY year DESC, votes DESC`,
    )
    .all(chamber, district) as { year: number; candidate: string; party: string | null; votes: number }[];
  const byYear = new Map<number, typeof rows>();
  for (const r of rows) {
    if (!byYear.has(r.year)) byYear.set(r.year, []);
    byYear.get(r.year)!.push(r);
  }
  return [...byYear.entries()].map(([year, candidates]) => {
    const total = candidates.reduce((s, c) => s + c.votes, 0);
    return { year, total, candidates };
  });
};

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

/** "Since taking office": first day of the month of the member's first
 * recorded floor vote. Vote records begin 2009, CFIS records 2008, so
 * long-serving members' windows start at the records floor, not their
 * real swearing-in. Members seated too recently to have voted fall back
 * to the newest session's start. */
const _sessionStart = () =>
  ((db.prepare("SELECT MAX(substr(id, 1, 4)) AS y FROM sessions").get() as { y: string }).y ?? "2025")
  + "-01-01";
export const officeEntryFor = (personId: string): string => {
  const row = db
    .prepare(
      `SELECT substr(MIN(e.date), 1, 7) || '-01' AS since
       FROM vote_records r JOIN vote_events e ON e.id = r.vote_event_id
       WHERE r.person_id = ?`,
    )
    .get(personId) as { since: string | null };
  return row?.since ?? _sessionStart();
};

// windows every contribution row to the recipient's time in office;
// MATERIALIZED so the per-person subquery runs once per query, not once
// per contribution row
const ENTRY_CTE = `WITH entry AS MATERIALIZED (
  SELECT p.id AS id, COALESCE(
    (SELECT substr(MIN(e.date), 1, 7) || '-01'
     FROM vote_records r JOIN vote_events e ON e.id = r.vote_event_id
     WHERE r.person_id = p.id), @fb) AS since
  FROM people p
)`;
const WINDOWED = `contributions c JOIN entry ON entry.id = c.person_id AND c.date >= entry.since
  AND c.date >= @start AND c.date <= @end`;

/** Campaign money summary for one legislator, windowed to their time in
 * office. Three honest states: null = no committee mapped (say "not
 * linked", never "$0"); {total: 0} = mapped but no receipts; else data. */
export const moneyFor = (personId: string) => {
  // a mapping with zero receipts across all recorded history means the
  // member's active committee isn't linked yet (surname-only committee
  // names never auto-match); show the coverage gap, never a false $0
  const mapped = db
    .prepare("SELECT COUNT(*) AS n FROM contributions WHERE person_id = ?")
    .get(personId) as { n: number };
  if (mapped.n === 0) return null;
  const entry = officeEntryFor(personId);
  const summary = db
    .prepare(
      `SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total,
              MIN(date) AS first, MAX(date) AS last
       FROM contributions WHERE person_id = ? AND date >= ?`,
    )
    .get(personId, entry) as { n: number; total: number; first: string | null; last: string | null };
  // committee donors grouped by CFIS entity id (collision-proof), never name
  const committees = db
    .prepare(
      `SELECT from_entity_id AS entityId, MAX(from_name) AS name,
              SUM(amount) AS total, COUNT(*) AS n
       FROM contributions
       WHERE person_id = ? AND date >= ? AND from_type = 'Registrant' AND from_entity_id IS NOT NULL
       GROUP BY from_entity_id ORDER BY total DESC LIMIT 5`,
    )
    .all(personId, entry) as { entityId: number; name: string; total: number; n: number }[];
  const occupations = db
    .prepare(
      `SELECT occupation, SUM(amount) AS total, COUNT(*) AS n
       FROM contributions
       WHERE person_id = ? AND date >= ? AND from_type = 'Individual'
       AND occupation IS NOT NULL AND TRIM(occupation) != ''
       GROUP BY LOWER(TRIM(occupation)) ORDER BY total DESC LIMIT 5`,
    )
    .all(personId, entry) as { occupation: string; total: number; n: number }[];
  for (const o of occupations) o.occupation = deShout(o.occupation);
  const individualTotal = db
    .prepare(
      "SELECT COALESCE(SUM(amount), 0) AS t FROM contributions"
      + " WHERE person_id = ? AND date >= ? AND from_type = 'Individual'",
    )
    .get(personId, entry) as { t: number };
  return { ...summary, entry, committees, occupations, individualTotal: individualTotal.t };
};

/** Statewide rollup of the same contribution data shown on profiles,
 * each member's receipts windowed to their time in office, optionally
 * intersected with an election-cycle date range. Covers only
 * legislators with a linked committee; rankings compare within that
 * covered set, never beyond it. */
export const moneyOverview = (bounds?: { start: string; end: string }) => {
  const P = {
    fb: _sessionStart(),
    start: bounds?.start ?? "0000",
    end: bounds?.end ?? "9999",
  };
  const summary = db
    .prepare(
      `${ENTRY_CTE}
       SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total,
              MIN(c.date) AS first, MAX(c.date) AS last
       FROM ${WINDOWED}`,
    )
    .get(P) as { n: number; total: number; first: string | null; last: string | null };
  // covered = members whose linked committees actually carry receipts; a
  // receipt-less mapping is an incomplete link, not coverage
  const covered = db
    .prepare("SELECT COUNT(DISTINCT person_id) AS n FROM contributions")
    .get() as { n: number };
  const sitting = db
    .prepare(
      "SELECT COUNT(*) AS n FROM people WHERE current_role IN ('Representative', 'Senator')",
    )
    .get() as { n: number };
  const individuals = db
    .prepare(
      `${ENTRY_CTE}
       SELECT COALESCE(SUM(amount), 0) AS t,
              COALESCE(SUM(CASE WHEN amount < 200 THEN amount ELSE 0 END), 0) AS small
       FROM ${WINDOWED} WHERE c.from_type = 'Individual'`,
    )
    .get(P) as { t: number; small: number };
  const committeeTotal = (
    db
      .prepare(
        `${ENTRY_CTE} SELECT COALESCE(SUM(amount), 0) AS t FROM ${WINDOWED}
         WHERE c.from_type = 'Registrant'`,
      )
      .get(P) as { t: number }
  ).t;
  const topCommittees = db
    .prepare(
      `${ENTRY_CTE}
       SELECT c.from_entity_id AS entityId, MAX(c.from_name) AS name,
              SUM(c.amount) AS total, COUNT(*) AS n,
              COUNT(DISTINCT c.person_id) AS recipients
       FROM ${WINDOWED}
       WHERE c.from_type = 'Registrant' AND c.from_entity_id IS NOT NULL
       GROUP BY c.from_entity_id ORDER BY total DESC LIMIT 15`,
    )
    .all(P) as { entityId: number; name: string; total: number; n: number; recipients: number }[];
  // breadth: who reaches the most members, regardless of dollar size
  const widestCommittees = db
    .prepare(
      `${ENTRY_CTE}
       SELECT c.from_entity_id AS entityId, MAX(c.from_name) AS name,
              SUM(c.amount) AS total, COUNT(DISTINCT c.person_id) AS recipients
       FROM ${WINDOWED}
       WHERE c.from_type = 'Registrant' AND c.from_entity_id IS NOT NULL
       GROUP BY c.from_entity_id ORDER BY recipients DESC, total DESC LIMIT 10`,
    )
    .all(P) as { entityId: number; name: string; total: number; recipients: number }[];
  const topLegislators = db
    .prepare(
      `${ENTRY_CTE}
       SELECT c.person_id AS id, p.name, p.party, p.chamber, p.district,
              SUM(c.amount) AS total, COUNT(*) AS n
       FROM ${WINDOWED} JOIN people p ON p.id = c.person_id
       GROUP BY c.person_id ORDER BY total DESC LIMIT 15`,
    )
    .all(P) as {
      id: string; name: string; party: string | null; chamber: string | null;
      district: string | null; total: number; n: number;
    }[];
  const byParty = db
    .prepare(
      `${ENTRY_CTE}
       SELECT p.party, COALESCE(SUM(c.amount), 0) AS total,
              COUNT(DISTINCT c.person_id) AS legislators
       FROM ${WINDOWED} JOIN people p ON p.id = c.person_id
       GROUP BY p.party ORDER BY total DESC`,
    )
    .all(P) as { party: string | null; total: number; legislators: number }[];
  const topOccupations = db
    .prepare(
      `${ENTRY_CTE}
       SELECT c.occupation AS occupation, SUM(c.amount) AS total, COUNT(*) AS n
       FROM ${WINDOWED}
       WHERE c.from_type = 'Individual'
       AND c.occupation IS NOT NULL AND TRIM(c.occupation) != ''
       GROUP BY LOWER(TRIM(c.occupation)) ORDER BY total DESC LIMIT 10`,
    )
    .all(P) as { occupation: string; total: number; n: number }[];
  for (const o of topOccupations) o.occupation = deShout(o.occupation);
  return {
    ...summary, covered: covered.n, sitting: sitting.n,
    individualTotal: individuals.t, smallDollarTotal: individuals.small,
    committeeTotal,
    topCommittees, widestCommittees, topLegislators, byParty, topOccupations,
  };
};

/** Organizations registered as lobbying on a bill (an interest
 * registration, not a for/against position). */
export const lobbyingFor = (billId: string) =>
  db
    .prepare(
      `SELECT principal_id, principal, source_url FROM lobbying_interests
       WHERE bill_id = ? ORDER BY principal`,
    )
    .all(billId) as { principal_id: number; principal: string; source_url: string | null }[];

export const sessionStats = (sessionId: string) =>
  db
    .prepare(
      `SELECT COUNT(*) AS bills,
              SUM(CASE WHEN status = 'enacted' THEN 1 ELSE 0 END) AS enacted,
              SUM(CASE WHEN status = 'vetoed' THEN 1 ELSE 0 END) AS vetoed,
              SUM(died_without_hearing) AS graveyard
       FROM bills WHERE session_id = ?`,
    )
    .get(sessionId) as { bills: number; enacted: number; vetoed: number; graveyard: number };
