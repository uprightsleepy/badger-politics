export const STATUS_LABELS: Record<string, string> = {
  introduced: "Introduced",
  in_committee: "In committee",
  passed_chamber: "Passed one chamber",
  passed: "Passed both chambers",
  adopted: "Adopted",
  enacted: "Became law",
  vetoed: "Vetoed",
  failed_sjr1: "Died at session end",
};

export const STATUS_SHORT: Record<string, string> = {
  introduced: "Introduced",
  in_committee: "In committee",
  passed_chamber: "Passed 1 house",
  passed: "Passed both",
  adopted: "Adopted",
  enacted: "Law",
  vetoed: "Vetoed",
  failed_sjr1: "Died",
};

export const STATUS_STYLES: Record<string, string> = {
  introduced: "bg-navy-50 text-navy-700",
  in_committee: "bg-gold-100 text-navy-800",
  passed_chamber: "bg-navy-100 text-navy-800",
  passed: "bg-navy-100 text-navy-800",
  adopted: "bg-moss-50 text-moss-600",
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

/** Bill titles all open "Relating to: ..."; strip it for compact rows. */
export const shortTitle = (title: string | null): string =>
  (title ?? "")
    // 273 titles carry a double space after the prefix; some omit it entirely
    .replace(/^\s*relating to:\s*/i, "")
    .replace(/^./, (c) => c.toUpperCase());

/** Committee page slug: the tail of the scraped committee id. */
export const committeeSlug = (id: string): string => id.split("/").pop()!;

export const roleAbbr = (chamber: string | null): string =>
  chamber === "upper" ? "SD" : "AD";

export const chamberName = (chamber: string | null): string =>
  chamber === "lower" ? "Assembly" : chamber === "upper" ? "Senate" : "Legislature";

/** One display-name rule for a hearing, shared by the calendar JSON and
 * the hearings list so the same event never shows two names. */
export const hearingDisplayName = (h: {
  committee_name: string | null;
  committee_chamber: string | null;
  title: string | null;
}): string =>
  h.committee_name
    ? `${h.committee_chamber ? `${chamberName(h.committee_chamber)} ` : ""}${h.committee_name}`
    : (h.title ?? "Committee hearing");

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

export const fmtMoney = (v: number): string =>
  "$" + Math.round(v).toLocaleString("en-US");

// the state's index terms encode em dashes as " _ "; restore for display
export const subjectDisplay = (subject: string): string =>
  subject
    .split(" _ ")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" — ");

export const subjectSlug = (subject: string): string =>
  subject.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const monthYear = (iso: string): string =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

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

// statutory compensation (s. 20.923); salary is identical for every member
export const COMPENSATION = {
  salary: 60924,
  assembly: { overnight: 171, day: 85.5 },
  senate: { overnight: 140, note: "half rate for Dane County members" },
};

/** How a bill becomes law: the stepper's stations, derived from status.
 * Resolutions never go to the governor, so their track ends at adoption. */
export function stepperState(
  status: string | null,
  chamber: string | null,
  classification: string | null = null,
) {
  const first = chamber === "upper" ? "Senate" : "Assembly";
  const second = chamber === "upper" ? "Assembly" : "Senate";
  const isResolution = classification?.includes("resolution") ?? false;
  const oneHouse = isResolution && !(classification ?? "").includes("joint");
  const steps = isResolution
    ? [
        { label: "Introduced" },
        { label: `Passes ${first}` },
        ...(oneHouse ? [] : [{ label: `Passes ${second}` }]),
        { label: "Adopted" },
      ]
    : [
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
    adopted: steps.length,
    failed_sjr1: 1,
    vetoed: 3,
    enacted: 5,
  };
  // a one-house resolution is fully adopted at "passed one chamber"
  if (oneHouse && status === "passed_chamber") {
    return { steps, reached: steps.length, failed: false };
  }
  const failed = status === "failed_sjr1" || status === "vetoed";
  return { steps, reached: reached[status ?? "introduced"] ?? 1, failed };
}
