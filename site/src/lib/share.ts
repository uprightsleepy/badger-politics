/** Per-page share cards. The build writes their text to /og/cards.json and
 * scripts/share-cards.mjs renders each to a PNG at its `image` path.
 *
 * Only the pages people share get one, which keeps the render to a few
 * minutes: bills of the newest two bienniums, sitting legislators, and 2026
 * races. Every other page keeps the sitewide /og.png, and so do LegiScan's
 * bills: an image has no room for the credit their records carry
 * (lib/legiscan). The same subset gets an /embed/ card. */
import { once } from "./connection.ts";
import { actionsFor, allSessions, bienniumOf, builtSessions, billsFor, meta, races2026, sittingPeople } from "./db.ts";
import type { Bill, Person } from "./db.ts";
import { tellStory } from "./billStory.ts";
import {
  billSlug, chamberName, clip, identifierLong, partyWord, personSlug, sessionPlainName, shortTitle,
  STATUS_LABELS,
} from "./format.ts";
import { isLegiscan } from "./legiscan.ts";

export interface ShareCard {
  /** Site path of the PNG, and of the card in the manifest. */
  image: string;
  alt: string;
  kicker: string;
  title: string;
  detail: string;
}

const card = (image: string, kicker: string, title: string, detail: string): ShareCard => ({
  image, kicker, title, detail,
  alt: `${kicker}. ${title.replace(/[.…]$/, "")}. ${detail}.`,
});

const recentBienniums = once(() => {
  const newest = Math.max(...allSessions().map((s) => bienniumOf(s.id)));
  return new Set([newest, newest - 2]);
});

/** Bills and members that get a share card and an embed. */
export const billShared = (bill: Bill): boolean =>
  !isLegiscan(bill) && recentBienniums().has(bienniumOf(bill.session_id));
export const personShared = (person: Person): boolean =>
  person.current_role === "Representative" || person.current_role === "Senator";

export const billCard = (bill: Bill, sessionName: string): ShareCard | undefined => {
  if (!billShared(bill)) return undefined;
  // judged as of the snapshot, exactly as the bill page does
  const asOf = (meta().imported_at ?? new Date().toISOString()).slice(0, 10);
  const status = tellStory(bill, actionsFor(bill.id), asOf).status;
  const subject = shortTitle(bill.title).replace(/\.\s*$/, "") || identifierLong(bill.identifier);
  return card(
    `/og/bills/${bill.session_id}/${billSlug(bill.identifier)}.png`,
    `${identifierLong(bill.identifier)}, ${sessionPlainName(bill.session_id, sessionName)}`,
    clip(subject, 120),
    STATUS_LABELS[status] ?? "Introduced",
  );
};

export const personCard = (person: Person): ShareCard | undefined =>
  personShared(person)
    ? card(
        `/og/legislators/${personSlug(person.id)}.png`,
        person.chamber === "upper" ? "State senator" : "State representative",
        person.name,
        `${chamberName(person.chamber)} District ${person.district}, ${partyWord(person.party)}`,
      )
    : undefined;

export const raceCard = (person: Person): ShareCard => {
  const seat = `${person.chamber === "upper" ? "senate" : "assembly"}-${person.district}`;
  return card(
    `/og/elections/2026/${seat}.png`,
    "2026 election",
    `${chamberName(person.chamber)} District ${person.district}`,
    "On the ballot November 3, 2026",
  );
};

/** Every card this build links to, for the renderer. */
export const shareCards = (): ShareCard[] => [
  ...builtSessions().flatMap((s) =>
    billsFor(s.id).flatMap((b) => billCard(b, s.name ?? s.id) ?? []),
  ),
  ...sittingPeople().flatMap((p) => personCard(p) ?? []),
  ...races2026().map(raceCard),
];
