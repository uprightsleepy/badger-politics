/** Shared shape of a subject or topic page: what happened to its bills, and
 * the bills by session, newest first, in the order the site lists sessions. */
import { allSessions, type Bill } from "./db";
import { sessionPlainName } from "./format";
import { leadSentence } from "./billRows";

export const subjectLead = (bills: Bill[]): string =>
  leadSentence({
    total: bills.length,
    enacted: bills.filter((b) => b.status === "enacted").length,
    vetoed: bills.filter((b) => b.status === "vetoed").length,
    noHearing: bills.filter((b) => b.died_without_hearing === 1).length,
  });

export const bySessionSpan = (bills: Bill[]) => {
  const order = allSessions();
  const rank = new Map(order.map((s, i) => [s.id, i]));
  const nameOf = new Map(order.map((s) => [s.id, sessionPlainName(s.id, s.name)]));
  const sessionName = (id: string) => nameOf.get(id) ?? sessionPlainName(id, `${id} session`);
  const bySession = [...Map.groupBy(bills, (b) => b.session_id)]
    .sort((a, b) => (rank.get(a[0]) ?? 1e9) - (rank.get(b[0]) ?? 1e9) || b[0].localeCompare(a[0]));
  const span = bySession.length > 1
    ? ` They span ${bySession.length.toLocaleString()} sessions, from the ${sessionName(bySession.at(-1)![0])} to the ${sessionName(bySession[0][0])}.`
    : bySession.length === 1
      ? bills.length === 1 ? ` It's from the ${sessionName(bySession[0][0])}.` : ` All are from the ${sessionName(bySession[0][0])}.`
      : "";
  return { bySession, sessionName, span };
};
