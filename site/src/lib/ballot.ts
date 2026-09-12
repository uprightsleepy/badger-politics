/** What the Elections Commission's ballot-access report says about a
 * sitting member's seat. The report is the only source: a row with no
 * status posted yet is "pending", never read as a retirement or as a
 * candidacy. Client scripts import this too, so it reads no database. */
export const ELECTION_CYCLE = 2026;

export type BallotStatus =
  | { kind: "on-ballot" | "not-running" | "pending" | "future"; year: number }
  | { kind: "none" };

export const ballotStatus = (
  election: { cycle_year: number; on_ballot: number | null } | null | undefined,
  cycle: number = ELECTION_CYCLE,
): BallotStatus => {
  if (!election) return { kind: "none" };
  const year = election.cycle_year;
  if (year !== cycle) return { kind: "future", year };
  const kind =
    election.on_ballot === 1 ? "on-ballot" : election.on_ballot === 0 ? "not-running" : "pending";
  return { kind, year };
};
