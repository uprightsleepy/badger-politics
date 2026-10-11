/** Today's date in Wisconsin as YYYY-MM-DD ("en-CA" formats that way).
 * Record dates are Wisconsin dates; a UTC date runs a day ahead every
 * evening. Browser-safe. */
export const wisconsinToday = (now = new Date()): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "America/Chicago" }).format(now);
