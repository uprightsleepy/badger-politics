/** How often two lawmakers voted the same way, counted from a session's
 * vote matrix: one string per member, one character per roll call.
 * Only Aye ("y") and No ("n") compare; an absence, an excusal or a
 * not-voting (".") on either side leaves that roll call out. A plain
 * count, never a score. Browser-safe: no database. */

export const voteChar = (option: string | null | undefined): string =>
  option === "yes" ? "y" : option === "no" ? "n" : ".";

export interface Agreement {
  /** Roll calls where both voted Aye or No. */
  shared: number;
  /** Of those, the ones where they voted the same way. */
  same: number;
  /** Indexes of the shared roll calls where they voted differently. */
  differed: number[];
}

export function compareVotes(a: string, b: string): Agreement {
  const out: Agreement = { shared: 0, same: 0, differed: [] };
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    if (a[i] === "." || b[i] === ".") continue;
    out.shared += 1;
    if (a[i] === b[i]) out.same += 1;
    else out.differed.push(i);
  }
  return out;
}
