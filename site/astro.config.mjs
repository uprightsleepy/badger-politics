import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import Database from "better-sqlite3";
import tailwindcss from "@tailwindcss/vite";

// Real lastmod values, from the Legislature's own action dates. A nightly
// build timestamp on 23,000 URLs tells a crawler that everything changed
// every night, which is both false and useless. A bill whose last action
// was in 2011 should say so.
const lastmod = new Map();
try {
  const db = new Database(fileURLToPath(new URL("../data/wi.sqlite", import.meta.url)), {
    readonly: true,
  });
  const rows = db
    .prepare(
      "SELECT session_id, identifier, latest_action_date FROM bills" +
        " WHERE source != 'legiscan' AND latest_action_date IS NOT NULL",
    )
    .all();
  for (const r of rows) {
    const slug = r.identifier.replace(/\s+/g, "").toLowerCase();
    lastmod.set(`/bills/${r.session_id}/${slug}/`, r.latest_action_date);
  }
  db.close();
} catch {
  // A pull request typechecks against an empty schema and has no snapshot.
  // Omitting lastmod is correct there; a wrong date would be worse.
}

export default defineConfig({
  site: "https://badgerpolitics.org",
  output: "static",
  integrations: [
    sitemap({
      // ~23,500 URLs after roll calls are excluded; sharded because
      // 50,000 per file is the limit search engines accept.
      entryLimit: 20000,
      filter: (page) =>
        // the /hearings redirect stub is a meta-refresh with no content
        (!page.includes("/hearings/") || page.endsWith("/calendar/")) &&
        // roll-call pages and the per-member full-record pages carry
        // noindex; listing them here would ask a crawler to fetch what it
        // has been told not to index
        !/\/votes\//.test(page) &&
        !/\/legislators\/[^/]+\/(votes|bills)\//.test(page),
      serialize(item) {
        // bills and members change as the session moves; reference pages
        // rarely do. Priority is relative within our own site only.
        const path = new URL(item.url).pathname;
        const known = lastmod.get(path);
        if (known) item = { ...item, lastmod: new Date(`${known}T00:00:00Z`).toISOString() };
        if (path === "/") return { ...item, changefreq: "daily", priority: 1.0 };
        if (/^\/(bills|votes)\//.test(path)) {
          return { ...item, changefreq: "weekly", priority: 0.8 };
        }
        if (/^\/(legislators|committees|districts|money|lobbying|local|federal)\//.test(path)) {
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
