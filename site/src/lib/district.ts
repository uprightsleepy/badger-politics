/** The one reader for the locally saved districts. Values are validated
 * as integers in range (Assembly 1-99, Senate 1-33); anything malformed
 * self-heals by clearing the key and reporting nothing saved. */
export const savedDistrict = (): { ad: number; sd: number } | null => {
  try {
    const raw = localStorage.getItem("bp-district");
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
    localStorage.removeItem("bp-district");
    return null;
  }
};
