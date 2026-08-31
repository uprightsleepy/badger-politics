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

/** Pill colour for a recorded position. Each chamber has its own
 * vocabulary (Yea/Nay in the Senate, Aye/No in the House, Guilty/Not
 * Guilty on impeachment), so the sets are the importer's. */
export const castStyle = (cast: string): string =>
  ["Yea", "Aye", "Guilty"].includes(cast)
    ? "bg-moss-50 text-moss-600"
    : ["Nay", "No", "Not Guilty"].includes(cast)
      ? "bg-badger-50 text-badger-700"
      : "bg-navy-50 text-navy-600";

/** "112th (2011-12)": the first year of a Congress is 1789 + 2(n-1). */
export const congressLabel = (congress: number): string => {
  const start = 1789 + (congress - 1) * 2;
  return `${congress}th (${start}–${String(start + 1).slice(2)})`;
};
