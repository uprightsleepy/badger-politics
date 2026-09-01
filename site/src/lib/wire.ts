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
  authored: { total: number; signedOn: number; enacted: number; vetoed: number; noHearing: number };
  election: { cycle_year: number; on_ballot: number | null } | null;
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
export type RepSummaries = {
  assembly: Record<string, RepSummary>;
  senate: Record<string, RepSummary>;
};

/** /data/ballot-2026.json: what is on one district's ballot. */
export type Race = {
  district: number;
  onBallot: boolean;
  incumbent: { name: string; party: string | null; slug: string } | null;
  incumbentRunning: boolean;
  candidates: { name: string; party: string | null }[];
};
export type Ballot = {
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
    districts: Record<string, { name: string; slug: string }[]>;
  }
>;
