/** Shapes of the static JSON files the client scripts read.
 *
 * Each file is written by one endpoint under src/pages/data/ at build
 * time and read by one or more page scripts in the browser. Declaring
 * the shape once, here, means the writer and every reader are checked
 * against the same contract. */

/** /data/reps.json: district -> sitting member, for the my-reps cards. */
export type RepSlim = {
  name: string;
  party: string | null;
  slug: string;
  image: string | null;
};
export type Reps = { assembly: Record<string, RepSlim>; senate: Record<string, RepSlim> };

/** /data/rep-summaries.json: the quick-glance record behind each card. */
export type RepSummary = {
  name: string;
  party: string | null;
  slug: string;
  role: string | null;
  contact: { email: string; phone: string | null } | null;
  committees: { name: string; role: string; slug: string }[];
  attendance: { total: number; missed: number };
  /** Yes-or-no votes cast out of every roll call held while serving this
   * biennium; the rest are absences and recorded non-votes. */
  voted: { cast: number; total: number };
  authored: { total: number; signedOn: number; enacted: number; vetoed: number; noHearing: number };
  election: { cycle_year: number; on_ballot: number | null } | null;
  /** Approved filings for this seat's 2026 race, the member excluded. */
  opponents: { name: string; party: string | null }[];
  /** Parties whose primary for this seat may have a write-in nominee the
   * certified results don't name. */
  writeInPending: string[];
  /** The same primaries with the reason each nominee isn't settled. */
  writeInReasons?: { party: string; reason: string }[];
  /** Share of votes cast with their party's majority, newest regular
   * session with at least 20 such votes; null for members outside the two
   * caucuses. `label` is the session's plain name ("2025–26 session"). */
  loyalty: { pct: number; n: number; session: string; label: string } | null;
  recentVotes: {
    date: string | null;
    option: string;
    motion: string | null;
    identifier: string;
    slug: string;
    title: string | null;
    session: string;
    event: string;
  }[];
};
/** The middle half of a chamber's sitting members on one measure: the
 * yardstick a single member's number is read against. */
export type Typical = { low: number; high: number; max: number; members: number; session?: string };
export type RepSummaries = {
  assembly: Record<string, RepSummary>;
  senate: Record<string, RepSummary>;
  /** "general" once certified primary results name the November field. */
  phase?: "general" | "primary";
  /** Percent of votes not cast, and percent cast with the party. */
  typical?: Record<"assembly" | "senate", { notVoting: Typical | null; loyalty: Typical | null }>;
};

/** /data/ballot-2026.json: what is on one district's ballot. */
export type Race = {
  district: number;
  onBallot: boolean;
  incumbent: { name: string; party: string | null; slug: string } | null;
  incumbentRunning: boolean;
  /** As posted by the Elections Commission; "pending" is a gap, not a retirement. */
  incumbentStatus: "on-ballot" | "not-running" | "pending";
  candidates: { name: string; party: string | null }[];
  /** Why a party's nominee for this seat isn't settled, when one isn't. */
  writeIn?: string;
};
export type Ballot = {
  /** "general" once the certified primary names the November candidates. */
  phase: "general" | "primary";
  assembly: Record<string, Race>;
  senate: Record<string, Race>;
  statewide: Record<string, { name: string; party: string | null }[]>;
};

/** /data/local-reps.json: city-council rosters for the my-reps card. */
export type LocalReps = Record<
  string,
  {
    city: string;
    slug: string;
    council: string;
    districts: Record<string, { name: string; slug: string; image: string | null }[]>;
  }
>;

/** /data/agreement/{session}.json: each chamber's floor roll calls in the
 * session and how each sitting member voted on them, one character per
 * roll call ("y" Aye, "n" No, "." anything else; lib/agreement).
 * LegiScan's roll calls are left out (lib/legiscan). */
export type VoteMatrix = {
  /** [roll call id, date, bill identifier, motion], oldest first. */
  rollCalls: [string, string | null, string, string | null][];
  /** [slug, name, party, district], in the same order as `votes`. */
  members: [string, string, string | null, number | null][];
  votes: string[];
};
export type SessionVotes = { session: string; chambers: { upper?: VoteMatrix; lower?: VoteMatrix } };
