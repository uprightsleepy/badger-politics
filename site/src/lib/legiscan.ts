/** LegiScan, the fallback source for bills and roll calls the
 * Legislature's own pages can't supply.
 *
 * LegiScan licenses its API and datasets under Creative Commons
 * Attribution 4.0 (legiscan.com/legiscan and legiscan.com/gaits/datasets,
 * checked October 2026). The license lets the site show these records as
 * long as it credits LegiScan, links the license, says what was changed,
 * and links the source. So every page that shows one does all four.
 *
 * They still never go into the downloads, the JSON API or the feeds
 * (CLAUDE.md); that rule is unchanged. Browser-safe: no database. */

export const LEGISCAN_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/";
export const LEGISCAN_WI_URL = "https://legiscan.com/WI";

export const isLegiscan = (row: { source?: string | null }): boolean => row.source === "legiscan";

/** "AB 656" in the 2025 session -> legiscan.com/WI/bill/AB656/2025.
 * LegiScan numbers special-session bills differently, so those link to
 * its Wisconsin page instead of guessing an address. */
export const legiscanBillUrl = (sessionId: string, identifier: string): string =>
  /^\d{4}$/.test(sessionId)
    ? `https://legiscan.com/WI/bill/${identifier.replace(/\s+/g, "").toUpperCase()}/${sessionId}`
    : LEGISCAN_WI_URL;
