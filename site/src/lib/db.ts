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

export const bill = (id: string): Bill | undefined =>
  db.prepare("SELECT * FROM bills WHERE id = ?").get(id) as Bill | undefined;

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

export const voteEvent = (id: string): VoteEvent | undefined =>
  db.prepare("SELECT * FROM vote_events WHERE id = ?").get(id) as VoteEvent | undefined;

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

export const personVotes = (personId: string, limit = 4000) =>
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

export const upcomingHearings = (since: string) =>
  db
    .prepare(
      `SELECT h.*, c.name AS committee_name, c.chamber AS committee_chamber
       FROM hearings h LEFT JOIN committees c ON c.id = h.committee_id
       WHERE h.date >= ? ORDER BY h.date, h.time`,
    )
    .all(since) as Hearing[];

export const recentHearings = (limit = 40) =>
  db
    .prepare(
      `SELECT h.*, c.name AS committee_name, c.chamber AS committee_chamber
       FROM hearings h LEFT JOIN committees c ON c.id = h.committee_id
       ORDER BY h.date DESC, h.time DESC LIMIT ?`,
    )
    .all(limit) as Hearing[];

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
}

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
