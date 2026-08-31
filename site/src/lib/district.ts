/** The one module that touches the locally saved districts. The key
 * name lives here and nowhere else, so every reader, writer and "forget"
 * button agrees on it.
 *
 * Values are validated as integers in range (Assembly 1-99, Senate 1-33);
 * anything malformed self-heals by clearing the key and reporting
 * nothing saved. */
export type District = { ad: number; sd: number };

const KEY = "bp-district";

export const savedDistrict = (): District | null => {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const ad = Number(parsed?.ad);
    const sd = Number(parsed?.sd);
    if (
      !Number.isInteger(ad) || ad < 1 || ad > 99 ||
      !Number.isInteger(sd) || sd < 1 || sd > 33
    ) {
      throw new Error("saved district out of range");
    }
    return { ad, sd };
  } catch {
    localStorage.removeItem(KEY);
    return null;
  }
};

export const saveDistrict = (d: District): void => {
  localStorage.setItem(KEY, JSON.stringify(d));
};

export const forgetDistrict = (): void => {
  localStorage.removeItem(KEY);
};

/** How the reader's own things look everywhere: their reps, their
 * districts, their race. */
export const MINE_CLASS = "bg-gold-100 rounded px-1 font-semibold";

/** A spoken prefix for screen readers, ahead of the visible text. */
export const srPrefix = (el: Element, text: string): void => {
  const sr = document.createElement("span");
  sr.className = "sr-only";
  sr.textContent = text;
  el.prepend(sr);
};

/** Mark a link as the reader's own: the gold highlight plus its spoken label. */
export const markAsMine = (a: Element, srLabel: string): void => {
  a.classList.add(...MINE_CLASS.split(" "));
  srPrefix(a, srLabel);
};
