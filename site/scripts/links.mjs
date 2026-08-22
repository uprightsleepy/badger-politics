/** Link validator over the built site.
 * Internal links (and #fragment targets) are checked exhaustively against
 * dist/. External links are deduplicated and probed with polite, per-host
 * rate-limited requests when --external is passed.
 * Usage: node scripts/links.mjs [--external] [--external-limit N] */
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { DIST } from "./lib/serve.mjs";

// one walk records every path (files AND directories — a bare directory
// href counts as resolvable, as it always has) and yields the html files
const fsPaths = new Set();
async function* htmlFiles(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    fsPaths.add(path);
    if (entry.isDirectory()) yield* htmlFiles(path);
    else if (entry.name.endsWith(".html")) yield path;
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
  if (!fsPaths.has(f) && !fsPaths.has(f + ".html") && !fsPaths.has(join(DIST, path, "index.html"))) {
    failures++;
    console.log(`BROKEN internal ${path} (linked from ${seenOn})`);
  }
}

// fragment targets must exist as an id on the target page; the target is
// read raw (scripts included), exactly as the old per-fragment regex saw it
for (const [target, frags] of fragments) {
  const f = toFile(target);
  const file = fsPaths.has(f) ? f : toFile(target + "/");
  if (!fsPaths.has(file)) continue; // already reported as broken path
  const html = await readFile(file, "utf-8");
  const ids = new Set([...html.matchAll(/id="([^"]*)"/g)].map((m) => m[1]));
  for (const [frag, seenOn] of frags) {
    if (!ids.has(frag)) {
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
  const hosts = [...byHost.values()];
  let nextHost = 0;
  const checkHost = async (list) => {
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
    for (const [i, [url, seenOn]] of list.entries()) {
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
      // per-host politeness pause; the host's last URL needs none
      if (i < list.length - 1) await new Promise((r) => setTimeout(r, 500));
    }
  };
  // bounded worker pool: per-host pacing is unchanged, but thousands of
  // hosts no longer open sockets all at once
  const POOL = 64;
  const worker = async () => {
    while (nextHost < hosts.length) await checkHost(hosts[nextHost++]);
  };
  await Promise.all(Array.from({ length: Math.min(POOL, hosts.length) }, worker));
  failures += extFailures;
  console.log(`external check done: ${extFailures} failures`);
}

console.log(failures ? `\n${failures} broken links` : "\nall checked links valid");
process.exit(failures ? 1 : 0);
