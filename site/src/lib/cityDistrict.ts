/** The reader's saved city-council district, for addresses inside a
 * covered city (Milwaukee, West Allis). Device-only, same as the state
 * districts; this module owns the key. */
export type CityDistrict = { t: string; d: number };

const KEY = "bp-city-district";

export const savedCityDistrict = (): CityDistrict | null => {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const d = Number(parsed?.d);
    if (typeof parsed?.t !== "string" || !Number.isInteger(d) || d < 1 || d > 15) {
      throw new Error("saved city district out of range");
    }
    return { t: parsed.t, d };
  } catch {
    localStorage.removeItem(KEY);
    return null;
  }
};

export const saveCityDistrict = (c: CityDistrict): void => {
  localStorage.setItem(KEY, JSON.stringify(c));
};

export const forgetCityDistrict = (): void => {
  localStorage.removeItem(KEY);
};
