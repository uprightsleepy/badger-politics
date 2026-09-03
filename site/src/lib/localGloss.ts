/** Plain-language glosses for what the clerks record. The records stay
 * verbatim in the data and on the clerk's pages; these say what the
 * words mean to a reader with no council background. An action with no
 * entry shows as recorded, with no gloss invented. */

const ACTIONS: Record<string, string> = {
  "adopted": "approved (resolutions are adopted)",
  "adopted as amended": "approved after changes",
  "adopted to deny": "the council formally denied the request",
  "passed": "approved (ordinances are passed)",
  "passed as amended": "approved after changes",
  "approved": "approved",
  "approved as amended": "approved after changes",
  "approved and placed on file": "approved, with the item then closed",
  "approved subject to the necessary requirement(s)": "approved once the stated conditions are met",
  "confirmed": "an appointment was approved",
  "granted": "the request was granted",
  "allowed": "the claim was allowed",
  "placed on file": "closed without further action: neither approved nor rejected",
  "paid and placed on file": "the claim was paid and the item closed",
  "denied": "rejected",
  "denied and placed on file": "rejected and the item closed",
  "disapproved": "rejected",
  "disallowed and indefinitely postponed": "rejected",
  "amended": "changed, with a later vote on the changed version",
  "amended (withdrawn)": "a proposed change was withdrawn",
  "substituted": "replaced with a rewritten version",
  "referred": "sent to a committee for review before the council decides",
  "referred to": "sent to a committee for review before the council decides",
  "assigned to": "sent to a committee for review before the council decides",
  "referred for legal action": "sent to the City Attorney",
  "referred for legal action to the city attorney": "sent to the City Attorney",
  "reconsidered and referred back": "reopened and sent back to a committee",
  "held": "kept for a later meeting",
  "held in council": "kept for a later council meeting",
  "postponed": "put off to a later meeting",
  "tabled": "set aside, with no decision",
  "not acted on": "left without a decision",
  "no action taken": "left without a decision",
  "taken from committee": "pulled back from a committee to the full council",
  "taken from file": "reopened after being closed",
  "veto overridden": "approved over the mayor's veto",
  "veto sustained": "the mayor's veto stood; the measure failed",
  "reconsidered": "voted on again",
  "reconsidered and entered in journal": "voted on again and recorded",
  "public hearing held": "the public was heard; no decision on that vote",
  "public hearing cancelled": "the scheduled hearing was cancelled",
  "heard in closed session": "discussed in a closed session",
  "discussed": "discussed, with no decision on that vote",
  "settled": "the claim was settled",
  "withdrawn": "withdrawn by whoever brought it",
  "revoked": "a license or permit was revoked",
  "suspend the rules": "the council set aside its usual procedure for this item",
  "issue a findings and recommendation": "a committee issued its findings and recommendation",
  "not returned by city attorney": "the City Attorney did not return the item",
  "not approved by city attorney": "the City Attorney did not approve the item",
  "returned to committee - signatures": "sent back to committee for signatures",
  "ordered on file": "closed without further action",
};

const VOTES: Record<string, string> = {
  "Aye": "voted yes",
  "No": "voted no",
  "Present": "attended but voted neither yes nor no",
  "Pres (virt)": "attended by video",
  "Abstain": "chose not to vote",
  "Excused": "absent with notice",
  "Absent": "absent",
  "Non-Voting": "took part without a vote (the presiding mayor)",
};

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");

/** A recorded action, readable: all-caps records come down to sentence case. */
export const actionLabel = (action: string): string => {
  const t = action.trim();
  return t === t.toUpperCase() && /[A-Z]/.test(t)
    ? t.charAt(0) + t.slice(1).toLowerCase()
    : t;
};

export const actionGloss = (action: string): string | undefined => ACTIONS[norm(action)];
export const voteGloss = (value: string): string | undefined => VOTES[value.trim()];

/** Glossary entries for the actions and vote values a page shows,
 * deduplicated, in the order they first appear. */
export const glossaryFor = (
  actions: Iterable<string>,
  values: Iterable<string> = [],
): { term: string; meaning: string }[] => {
  const out: { term: string; meaning: string }[] = [];
  const seen = new Set<string>();
  for (const a of actions) {
    const key = norm(a);
    const meaning = ACTIONS[key];
    if (meaning && !seen.has(key)) {
      seen.add(key);
      out.push({ term: actionLabel(a), meaning });
    }
  }
  for (const v of values) {
    const meaning = VOTES[v.trim()];
    if (meaning && !seen.has(`v:${v}`)) {
      seen.add(`v:${v}`);
      out.push({ term: v, meaning });
    }
  }
  return out;
};
