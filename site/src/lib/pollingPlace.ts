/** The reader's saved polling place: typed in by hand on /my-reps/ after
 * looking it up on MyVote, shown again on election days. Device-only,
 * like the districts; this module owns the key. */
import { store } from "./store.ts";

const KEY = "bp-polling";

export const savedPollingPlace = (): string | null => store.get(KEY);

export const savePollingPlace = (place: string): void => {
  store.set(KEY, place);
};

export const forgetPollingPlace = (): void => {
  store.remove(KEY);
};
