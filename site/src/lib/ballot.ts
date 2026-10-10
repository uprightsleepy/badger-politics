/** What the Elections Commission's ballot-access report says about a
 * sitting member's seat. The report is the only source: a row with no
 * status posted yet is "pending", never read as a retirement or as a
 * candidacy. Client scripts import this too, so it reads no database. */
export const ELECTION_CYCLE = 2026;

/** The Commission's office name for a legislative seat, as its records spell it. */
export const seatOffice = (chamber: string | null, district: number | null): string =>
  `${chamber === "upper" ? "STATE SENATOR" : "REPRESENTATIVE TO THE ASSEMBLY"} DISTRICT ${district}`;

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

/** Why a party's nominee isn't settled, in a sentence, from the
 * certified primary (importer/wec_primary.py names the reason). */
export const writeInSentence = (pending: { party: string; reason: string }[]): string =>
  pending
    .map(({ party, reason }) =>
      /tied/i.test(reason)
        ? `The ${party} primary ended in a tie, so its nominee isn't settled yet.`
        : /could exceed/i.test(reason)
          ? `In the ${party} primary, write-in votes could outnumber the leader's, so its nominee isn't settled yet.`
          : /qualified/i.test(reason)
            ? `The ${party} primary had no printed candidate, and a write-in candidate may have qualified.`
            : `The ${party} primary's nominee isn't settled yet.`,
    )
    .join(" ");
