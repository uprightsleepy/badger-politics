/** One council member's record: the member-scoped queries and the
 * derived facts the member page shows, shaped once. The body-level
 * readers (bodies, rosters, tenant stats) stay in db.ts. */
import { hasTable, prep } from "./connection.ts";
import type { LocalMember } from "./db.ts";
import { glossaryFor, isNoVote, isYesVote } from "./localGloss.ts";
import { yearPageStarts } from "./paging.ts";

/** Recent votes and motions shown inline; the complete record is paged. */
export const RECENT = 300;

/** One member's positions on the items with dissent, newest first, each
 * with the council's tally; the test runs in SQLite so a long career
 * never loads whole. */
export const localMemberVotesWithDissent = (tenant: string, personId: number) =>
  prep(
      `SELECT v.value, v.event_item_id, a.matter_file, a.matter_url, a.title,
              a.action, e.date, e.insite_url, t.ayes, t.noes
       FROM local_votes v
       JOIN (SELECT tenant, event_item_id,
                    SUM(value IN ('Aye', 'Yes')) AS ayes, SUM(value IN ('No', 'Nay')) AS noes
             FROM local_votes WHERE tenant = ?
             GROUP BY event_item_id HAVING ayes > 0 AND noes > 0) t
         ON t.tenant = v.tenant AND t.event_item_id = v.event_item_id
       JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
       JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
       WHERE v.tenant = ? AND v.person_id = ?
       ORDER BY e.date DESC, a.event_item_id DESC`,
    )
    .all(tenant, tenant, personId) as {
    value: string; event_item_id: number; matter_file: string | null;
    matter_url: string | null; title: string | null; action: string; date: string; insite_url: string;
    ayes: number; noes: number;
  }[];

export const localMemberVotes = (
  tenant: string, personId: number, limit: number, offset = 0,
) =>
  prep(
      `SELECT v.value, v.event_item_id, a.matter_file, a.matter_url, a.title,
              a.action, e.date, e.insite_url
       FROM local_votes v
       JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
       JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
       WHERE v.tenant = ? AND v.person_id = ?
       ORDER BY e.date DESC, a.event_item_id DESC LIMIT ? OFFSET ?`,
    )
    .all(tenant, personId, limit, offset) as {
    value: string; event_item_id: number; matter_file: string | null;
    matter_url: string | null; title: string | null; action: string; date: string; insite_url: string;
  }[];

/** A presiding officer's votes when the other recorded voters split evenly. */
export const localMemberTieBreaks = (tenant: string, personId: number) =>
  prep(
      `SELECT v.value, a.matter_file, a.matter_url, a.title, a.action, e.date, e.insite_url,
              t.ayes - (v.value IN ('Aye', 'Yes')) AS other_ayes,
              t.noes - (v.value IN ('No', 'Nay')) AS other_noes
       FROM local_votes v
       JOIN (SELECT event_item_id, SUM(value IN ('Aye', 'Yes')) AS ayes, SUM(value IN ('No', 'Nay')) AS noes
             FROM local_votes WHERE tenant = ? GROUP BY event_item_id) t
         ON t.event_item_id = v.event_item_id
       JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
       JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
       WHERE v.tenant = ? AND v.person_id = ? AND v.value IN ('Aye', 'Yes', 'No', 'Nay')
         AND t.ayes - (v.value IN ('Aye', 'Yes')) = t.noes - (v.value IN ('No', 'Nay'))
         AND t.ayes - (v.value IN ('Aye', 'Yes')) > 0
       ORDER BY e.date DESC`,
    ).all(tenant, tenant, personId) as {
    value: string; matter_file: string | null; matter_url: string | null;
    title: string | null; action: string; date: string; insite_url: string;
    other_ayes: number; other_noes: number;
  }[];

/** Vote counts per year, newest first; the member page turns these into
 * links to the first page of the paged record that holds each year. */
export const localMemberVoteYears = (tenant: string, personId: number) =>
  prep(
      `SELECT substr(e.date, 1, 4) AS year, COUNT(*) AS n
       FROM local_votes v
       JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
       JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
       WHERE v.tenant = ? AND v.person_id = ?
       GROUP BY year ORDER BY year DESC`,
    ).all(tenant, personId) as { year: string; n: number }[];

/** Votes opposite the clerk's outcome; omit items without an outcome flag. */
export const localMemberOutcomes = (tenant: string, personId: number) =>
  prep(
      `SELECT COALESCE(SUM((v.value IN ('No', 'Nay') AND a.passed = 1)
                        OR (v.value IN ('Aye', 'Yes') AND a.passed = 0)), 0) AS lost,
              COALESCE(SUM(v.value IN ('Aye', 'Yes', 'No', 'Nay') AND a.passed IS NOT NULL), 0) AS decided
       FROM local_votes v
       JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
       WHERE v.tenant = ? AND v.person_id = ?`,
    ).get(tenant, personId) as { lost: number; decided: number };

/** Items the council's record names this member as having moved. */
export const localMemberMotions = (tenant: string, personId: number, limit: number) =>
  prep(
      `SELECT a.event_item_id, a.matter_file, a.matter_url, a.title, a.action, a.passed,
              e.date, e.insite_url
       FROM local_actions a
       JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
       WHERE a.tenant = ? AND a.mover_id = ?
       ORDER BY e.date DESC, a.event_item_id DESC LIMIT ?`,
    ).all(tenant, personId, limit) as {
    event_item_id: number; matter_file: string | null; matter_url: string | null;
    title: string | null; action: string; passed: number | null; date: string; insite_url: string;
  }[];
export const localMemberMotionCount = (tenant: string, personId: number) =>
  (prep(`SELECT COUNT(*) AS n FROM local_actions WHERE tenant = ? AND mover_id = ?`)
    .get(tenant, personId) as { n: number }).n;

/** Attendance from the clerk's roll calls: meetings where the member is
 * listed, meetings recorded present, and every value as recorded. */
export interface LocalAttendance {
  meetings: number; present: number; values: { value: string; n: number }[];
}
export const localMemberAttendance = (tenant: string, personId: number): LocalAttendance => {
  if (!hasTable("local_rollcalls")) return { meetings: 0, present: 0, values: [] };
  const totals = prep(
    `SELECT COUNT(DISTINCT event_id) AS meetings,
            COUNT(DISTINCT CASE WHEN value IN ('Present', 'Pres (virt)') THEN event_id END)
              AS present
     FROM local_rollcalls WHERE tenant = ? AND person_id = ?`,
  ).get(tenant, personId) as { meetings: number; present: number };
  const values = prep(
    `SELECT value, COUNT(*) AS n FROM local_rollcalls WHERE tenant = ? AND person_id = ?
     GROUP BY value ORDER BY n DESC`,
  ).all(tenant, personId) as { value: string; n: number }[];
  return { ...totals, values };
};

export const localMemberVoteStats = (tenant: string, personId: number) =>
  prep(
      `SELECT COUNT(*) AS total,
              COALESCE(SUM(v.value IN ('No', 'Nay')), 0) AS noes,
              COALESCE(SUM(v.value NOT IN ('Aye', 'Yes', 'No', 'Nay')), 0) AS other,
              MAX(e.date) AS last
       FROM local_votes v
       JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
       JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
       WHERE v.tenant = ? AND v.person_id = ?`,
    )
    .get(tenant, personId) as {
    total: number; noes: number; other: number; last: string | null;
  };

/** Every body a sitting member serves on besides the council, from the
 * tenant's own office records, chairs first. */
export const localMemberships = (tenant: string, personId: number) =>
  prep(
      `SELECT body_name, role, start, end, body_url FROM local_memberships
       WHERE tenant = ? AND person_id = ?
       ORDER BY CASE WHEN role LIKE '%Chair%' THEN 0 ELSE 1 END, body_name`,
    )
    .all(tenant, personId) as {
    body_name: string; role: string | null; start: string | null;
    end: string | null; body_url: string | null;
  }[];

export const localMemberTerms = (tenant: string, personId: number) =>
  prep(
      `SELECT title, start, end FROM local_member_terms
       WHERE tenant = ? AND person_id = ? ORDER BY start`,
    )
    .all(tenant, personId) as { title: string | null; start: string; end: string | null }[];

const yearsOf = (rows: { date: string }[]) => {
  const by = new Map<string, number>();
  for (const r of rows) by.set(r.date.slice(0, 4), (by.get(r.date.slice(0, 4)) ?? 0) + 1);
  return [...by.entries()].map(([year, n]) => ({ year, n }))
    .sort((a, b) => b.year.localeCompare(a.year));
};

export const councilMemberProfile = (tenant: string, member: LocalMember) => {
  const id = member.person_id;
  const stats = localMemberVoteStats(tenant, id);
  const votes = localMemberVotes(tenant, id, RECENT);
  const dissentVotes = localMemberVotesWithDissent(tenant, id);
  const terms = localMemberTerms(tenant, id);
  const soleNoes = dissentVotes.filter((v) => isNoVote(v.value) && v.noes === 1);
  const motionCount = localMemberMotionCount(tenant, id);
  const motions = motionCount > 0 ? localMemberMotions(tenant, id, RECENT) : [];
  const attendance = localMemberAttendance(tenant, id);
  // the seat is filled at the April spring election of the year the term ends
  const termEnd = member.is_current
    ? terms.map((t) => t.end).filter((e): e is string => !!e).sort().at(-1) ?? null
    : null;
  // Mayors preside; council presidents still vote as alderpersons.
  const presiding = terms.some((t) => t.title === "Mayor");
  const tieBreaks = presiding ? localMemberTieBreaks(tenant, id) : [];
  const tieAyes = tieBreaks.filter((v) => isYesVote(v.value)).length;
  return {
    stats,
    votes,
    dissentVotes,
    soleNoes,
    terms,
    committees: member.is_current ? localMemberships(tenant, id) : [],
    outcomes: localMemberOutcomes(tenant, id),
    motionCount,
    motions,
    attendance,
    termEnd,
    springYear: termEnd && termEnd.slice(5, 7) === "04" ? termEnd.slice(0, 4) : null,
    yearPages: yearPageStarts(localMemberVoteYears(tenant, id)),
    presiding,
    rated: !presiding,
    tieBreaks,
    // the chair's remaining Ayes joined an already unanimous council
    joinedAyes: stats.total - stats.noes - stats.other - tieAyes,
    years: { soleNoes: yearsOf(soleNoes), dissent: yearsOf(dissentVotes) },
    glossary: glossaryFor(
      [...tieBreaks, ...soleNoes, ...dissentVotes, ...votes, ...motions].map((r) => r.action),
      [
        ...new Set([...votes, ...dissentVotes].map((v) => v.value)),
        ...attendance.values.map((a) => a.value),
      ],
    ),
  };
};
export type CouncilMemberProfile = ReturnType<typeof councilMemberProfile>;
