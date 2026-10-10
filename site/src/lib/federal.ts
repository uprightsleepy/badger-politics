/** congress.gov path fragment for a Senate vote's document reference
 * ("S. 5271" -> "senate-bill/5271"), or null for document types with no
 * bill page (nominations, treaties). Mirrors the importer's DOC_PATHS. */
const DOC_PATHS: Record<string, string> = {
  "S.": "senate-bill",
  "S.Res.": "senate-resolution",
  "S.J.Res.": "senate-joint-resolution",
  "S.Con.Res.": "senate-concurrent-resolution",
  "H.R.": "house-bill",
  "H.Res.": "house-resolution",
  "H.J.Res.": "house-joint-resolution",
  "H.Con.Res.": "house-concurrent-resolution",
};

export const documentUrlFragment = (_congress: number, document: string): string | null => {
  const at = document.lastIndexOf(" ");
  if (at < 0) return null;
  const path = DOC_PATHS[document.slice(0, at)];
  return path ? `${path}/${document.slice(at + 1)}` : null;
};

/** A recorded position in words (docs/brand.md, "Plain words"). Each
 * chamber has its own vocabulary (Yea/Nay in the Senate, Aye/No in the
 * House, Guilty/Not Guilty on impeachment); the sets are the importer's. */
export const castWords = (cast: string): string =>
  ["Yea", "Aye"].includes(cast)
    ? "Voted yes"
    : ["Nay", "No"].includes(cast)
      ? "Voted no"
      : cast === "Not Voting"
        ? "Didn't vote"
        : `Voted ${cast.toLowerCase()}`;

/** 119 -> "119th", 121 -> "121st", 112 -> "112th" (as congress.gov spells it). */
export const ordinal = (n: number): string => {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
};

/** "112th Congress (2011–2012)": the first year of a Congress is 1789 + 2(n-1). */
export const congressLabel = (congress: number): string => {
  const start = 1789 + (congress - 1) * 2;
  return `${ordinal(congress)} Congress (${start}–${start + 1})`;
};

/** A term's end date in words: "January 3, 2031". */
export const longDate = (iso: string): string =>
  new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "long", day: "numeric", year: "numeric", timeZone: "UTC",
  });
