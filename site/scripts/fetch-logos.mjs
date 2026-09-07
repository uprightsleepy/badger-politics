/** Automatic logo retrieval was removed on 2026-09-07.
 * The previous helper crawled organization homepages without individual
 * robots.txt/terms reviews. Restore only after reviewing those sources and
 * logo.dev's current API, caching, attribution, and reuse terms.
 * Existing local assets remain; missing logos use the site's monogram tiles.
 */
console.log("fetch-logos: automatic retrieval paused pending source-policy review; using local assets");
