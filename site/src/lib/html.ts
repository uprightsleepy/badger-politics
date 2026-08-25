/** The one HTML escaper every set:html and innerHTML producer shares —
 * build-time and client scripts alike. A fix here reaches them all. */
export const esc = (s: string): string =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

/** Hrefs sourced from scraped or stored data: site-relative or http(s)
 * only; anything else (javascript:, data:, ...) renders as no link. */
export const safeHref = (url: string | null | undefined): string | null =>
  url && (/^https?:\/\//i.test(url) || url.startsWith("/")) ? url : null;
