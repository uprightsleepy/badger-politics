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
