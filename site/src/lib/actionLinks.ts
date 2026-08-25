/** Link legislator names inside verbatim bill-history text. The text is
 * never altered — names are only wrapped in profile links, and only when
 * the printed form resolves to exactly one member of the right chamber
 * in that session (the title before the name run fixes the chamber).
 * Ambiguous or unknown names stay plain text. */
import { sessionNameIndex } from "./db";
import { personSlug } from "./format";
import { esc } from "./html";

const TITLE_RE = /\b(Representative|Senator)s?\s+/g;
// one printed name: optional initial, then one or two capitalized words
// (compound surnames like "Bernard Schaber"); never swallows lowercase
// words such as "and" or "added"
const NAME_RE = /^(?:[A-Z]\.\s)?[A-Z][A-Za-z'’-]+(?:\s[A-Z][A-Za-z'’-]+)?/;
const SEP_RE = /^(,\s*(?:and\s+)?|\s+and\s+)/;

const norm = (s: string) => s.toLowerCase().replace(/[^a-z]/g, "");

export function linkifyAction(description: string, sessionId: string): string {
  const index = sessionNameIndex(sessionId);
  let html = "";
  let pos = 0;
  TITLE_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TITLE_RE.exec(description)) !== null) {
    const chamber = m[1] === "Representative" ? "lower" : "upper";
    const map = index[chamber];
    html += esc(description.slice(pos, TITLE_RE.lastIndex));
    pos = TITLE_RE.lastIndex;
    for (;;) {
      const rest = description.slice(pos);
      const name = NAME_RE.exec(rest);
      if (!name) break;
      const personId = map.get(norm(name[0]));
      if (personId) {
        html += `<a href="/legislators/${personSlug(personId)}/" class="underline">${esc(name[0])}</a>`;
      } else {
        html += esc(name[0]);
      }
      pos += name[0].length;
      const sep = SEP_RE.exec(description.slice(pos));
      if (!sep) break;
      html += esc(sep[0]);
      pos += sep[0].length;
    }
    TITLE_RE.lastIndex = pos;
  }
  html += esc(description.slice(pos));
  return html;
}
