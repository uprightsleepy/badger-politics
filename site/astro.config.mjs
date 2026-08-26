import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  site: "https://badgerpolitics.org",
  output: "static",
  integrations: [
    sitemap({
      // 44,000 URLs: split into shards with an index, which is also the
      // limit search engines accept per file.
      entryLimit: 20000,
      filter: (page) =>
        // the /hearings redirect stub is a meta-refresh with no content
        (!page.includes("/hearings/") || page.endsWith("/calendar/")) &&
        // roll-call pages carry noindex; listing them here would ask a
        // crawler to fetch what it has been told not to index
        !/\/votes\//.test(page),
      serialize(item) {
        // bills and members change as the session moves; reference pages
        // rarely do. Priority is relative within our own site only.
        const path = new URL(item.url).pathname;
        if (path === "/") return { ...item, changefreq: "daily", priority: 1.0 };
        if (/^\/(bills|votes)\//.test(path)) {
          return { ...item, changefreq: "weekly", priority: 0.8 };
        }
        if (/^\/(legislators|committees|districts|money|lobbying)\//.test(path)) {
          return { ...item, changefreq: "weekly", priority: 0.7 };
        }
        return { ...item, changefreq: "monthly", priority: 0.5 };
      },
    }),
  ],
  // Astro 7 defaults this to 'jsx', which drops the whitespace between a
  // text node and an inline element ("committee.<a>See every..."). Our
  // prose relies on HTML collapsing rules, so keep them.
  compressHTML: true,
  redirects: {
    // hearings folded into the calendar page; old links keep working
    "/hearings": "/calendar/#hearings",
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
