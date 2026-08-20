export const STATUS_LABELS: Record<string, string> = {
  introduced: "Introduced",
  in_committee: "In committee",
  passed_chamber: "Passed one chamber",
  passed: "Passed both chambers",
  enacted: "Became law",
  vetoed: "Vetoed",
  failed_sjr1: "Died at session end",
};

export const STATUS_STYLES: Record<string, string> = {
  introduced: "bg-navy-50 text-navy-700",
  in_committee: "bg-gold-100 text-navy-800",
  passed_chamber: "bg-navy-100 text-navy-800",
  passed: "bg-navy-100 text-navy-800",
  enacted: "bg-moss-50 text-moss-600",
  vetoed: "bg-badger-50 text-badger-700",
  failed_sjr1: "bg-badger-50 text-badger-700",
};

export const partyStyle = (party: string | null): string =>
  party === "Republican"
    ? "bg-badger-50 text-badger-700"
    : party === "Democratic"
      ? "bg-navy-50 text-navy-700"
      : "bg-gold-100 text-navy-800";

export const partyLetter = (party: string | null): string =>
  party ? party[0] : "?";

export const chamberName = (chamber: string | null): string =>
  chamber === "lower" ? "Assembly" : chamber === "upper" ? "Senate" : "Legislature";

export const billSlug = (identifier: string): string =>
  identifier.replace(/\s+/g, "").toLowerCase();

export const personSlug = (personId: string): string =>
  personId.replace(/^legacy\//, "legacy-").split("/").pop()!;

/** '13:01' (already America/Chicago) -> '1:01 PM' */
export const fmtTime = (t: string | null): string => {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  const h12 = h % 12 || 12;
  return `${h12}:${String(m).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"} CT`;
};

export const fmtDate = (iso: string | null): string => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
};

/** How a bill becomes law: the stepper's stations, derived from status. */
export function stepperState(status: string | null, chamber: string | null) {
  const first = chamber === "upper" ? "Senate" : "Assembly";
  const second = chamber === "upper" ? "Assembly" : "Senate";
  const steps = [
    { label: "Introduced" },
    { label: `Passes ${first}` },
    { label: `Passes ${second}` },
    { label: "Governor signs" },
    { label: "Law" },
  ];
  const reached: Record<string, number> = {
    introduced: 1,
    in_committee: 1,
    passed_chamber: 2,
    passed: 3,
    failed_sjr1: 1,
    vetoed: 3,
    enacted: 5,
  };
  const failed = status === "failed_sjr1" || status === "vetoed";
  return { steps, reached: reached[status ?? "introduced"] ?? 1, failed };
}
