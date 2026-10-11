/** Today's date in Wisconsin as YYYY-MM-DD ("en-CA" formats that way).
 * Record dates are Wisconsin dates; a UTC date runs a day ahead every
 * evening. Browser-safe. */
export const wisconsinToday = (now = new Date()): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(now);

/** The date `days` after (or before) a YYYY-MM-DD date. Calendar days, so
 * a daylight-saving change never shifts the answer. */
export const addDays = (iso: string, days: number): string => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
};
