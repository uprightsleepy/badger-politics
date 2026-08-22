/** Link validator over the built site.
 * Internal links (and #fragment targets) are checked exhaustively against
 * dist/. External links are deduplicated and probed with polite, per-host
 * rate-limited requests when --external is passed.
 * Usage: node scripts/links.mjs [--external] [--external-limit N] */
import { readFile, readdir, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";

const DIST = new URL("../dist", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");

async function* htmlFiles(dir) {
  for (const name of await readdir(dir)) {
    const path = join(dir, name);
    if ((await stat(path)).isDirectory()) yield* htmlFiles(path);
    else if (name.endsWith(".html")) yield path;
  }
}

const internal = new Map(); // href -> first page seen on
const external = new Map();
const fragments = new Map(); // href without fragment -> Set of fragments used
let pages = 0;

for await (const file of htmlFiles(DIST)) {
  pages++;
  // scripts hold template literals that look like hrefs; markup only
  const html = (await readFile(file, "utf-8")).replace(/<script[\s\S]*?<\/script>/g, "");
  const page = "/" + file.slice(DIST.length + 1).replaceAll("\\", "/");
  for (const m of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const url = m[1];
    if (url.startsWith("mailto:") || url.startsWith("data:") || url.startsWith("//")) continue;
    if (url.startsWith("http")) {
      if (!external.has(url)) external.set(url, page);
    } else if (url.startsWith("/")) {
      const [path, frag] = url.split("#");
      if (!internal.has(path || "/")) internal.set(path || "/", page);
      if (frag) {
        if (!fragments.has(path || page)) fragments.set(path || page, new Map());
        const fs = fragments.get(path || page);
        if (!fs.has(frag)) fs.set(frag, page);
      }
    } else if (url.startsWith("#")) {
      if (!fragments.has(page)) fragments.set(page, new Map());
      const fs = fragments.get(page);
      if (!fs.has(url.slice(1))) fs.set(url.slice(1), page);
    }
  }
}

let failures = 0;

// internal paths must resolve to a built file
const toFile = (p) => {
  const clean = decodeURIComponent(p.split("?")[0]);
  if (clean.endsWith("/")) return join(DIST, clean, "index.html");
  return join(DIST, clean);
};
for (const [path, seenOn] of internal) {
  const f = toFile(path);
  if (!existsSync(f) && !existsSync(f + ".html") && !existsSync(join(DIST, path, "index.html"))) {
    failures++;
    console.log(`BROKEN internal ${path} (linked from ${seenOn})`);
  }
}

// fragment targets must exist as an id on the target page
const dynamicFragments = new Set(); // ids created by client-side JS
for (const [target, frags] of fragments) {
  const f = toFile(target.endsWith(".html") ? target : target);
  const file = existsSync(f) ? f : toFile(target + "/");
  if (!existsSync(file)) continue; // already reported as broken path
  const html = await readFile(file, "utf-8");
  for (const [frag, seenOn] of frags) {
    if (!new RegExp(`id="${frag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`).test(html)) {
      failures++;
      console.log(`BROKEN fragment ${target}#${frag} (linked from ${seenOn})`);
    }
  }
}

console.log(`\ninternal: ${internal.size} unique paths, ${[...fragments.values()].reduce((s, m) => s + m.size, 0)} fragments, across ${pages} pages`);
console.log(`external: ${external.size} unique urls`);

if (process.argv.includes("--external")) {
  const limitIdx = process.argv.indexOf("--external-limit");
  const limit = limitIdx > -1 ? Number(process.argv[limitIdx + 1]) : Infinity;
  const urls = [...external.entries()].slice(0, limit);
  const byHost = new Map();
  for (const [url, seenOn] of urls) {
    const host = new URL(url).host;
    if (!byHost.has(host)) byHost.set(host, []);
    byHost.get(host).push([url, seenOn]);
  }
  console.log(`checking ${urls.length} external urls across ${byHost.size} hosts...`);
  let extFailures = 0;
  await Promise.all(
    [...byHost.entries()].map(async ([host, list]) => {
      const UA = { "User-Agent": "BadgerPolitics link check (badgerpolitics.org; hphil.work@gmail.com)" };
      const probe = async (url) => {
        let res = await fetch(url, { method: "HEAD", redirect: "follow",
          signal: AbortSignal.timeout(20000), headers: UA });
        if (res.status === 405 || res.status === 404 || res.status === 403) {
          res = await fetch(url, { method: "GET", redirect: "follow",
            signal: AbortSignal.timeout(20000), headers: UA });
        }
        return res;
      };
      for (const [url, seenOn] of list) {
        // one retry so transient timeouts on hours-long runs don't record
        let verdict = null;
        for (let attempt = 0; attempt < 2 && verdict === null; attempt++) {
          try {
            const res = await probe(url);
            if (res.ok) verdict = "ok";
            else if (attempt === 1) verdict = String(res.status);
            else await new Promise((r) => setTimeout(r, 5000));
          } catch (e) {
            if (attempt === 1) verdict = e.name;
            else await new Promise((r) => setTimeout(r, 5000));
          }
        }
        if (verdict !== "ok") {
          extFailures++;
          console.log(`BROKEN external ${verdict} ${url} (linked from ${seenOn})`);
        }
        await new Promise((r) => setTimeout(r, 500));
      }
    }),
  );
  failures += extFailures;
  console.log(`external check done: ${extFailures} failures`);
}

console.log(failures ? `\n${failures} broken links` : "\nall checked links valid");
process.exit(failures ? 1 : 0);
