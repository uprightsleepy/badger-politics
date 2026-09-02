/** Google Places (New) key for as-you-type address suggestions.
 *
 * Comes from the PUBLIC_PLACES_KEY build variable; with none set, the
 * suggestion code stays dormant and the site remains fully keyless. The
 * key lands in the public bundle by design, like any Maps browser key,
 * so it must be restricted in the Google Cloud console: Website
 * referrers https://badgerpolitics.org/* and
 * https://badgerpolitics-dev.web.app/*, API restriction "Places API
 * (New)" only. CI reads the repository Actions variable
 * PUBLIC_PLACES_KEY; locally a site/.env line does the same.
 */
export const PLACES_KEY: string = import.meta.env.PUBLIC_PLACES_KEY ?? "";
