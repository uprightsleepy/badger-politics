/** The reader's saved polling place: typed in by hand on /my-reps/ after
 * looking it up on MyVote, shown again on election days. Device-only,
 * like the districts; this module owns the key. */
const KEY = "bp-polling";

export const savedPollingPlace = (): string | null => localStorage.getItem(KEY);

export const savePollingPlace = (place: string): void => {
  localStorage.setItem(KEY, place);
};

export const forgetPollingPlace = (): void => {
  localStorage.removeItem(KEY);
};
