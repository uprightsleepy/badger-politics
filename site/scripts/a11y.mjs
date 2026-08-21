/** axe-core accessibility scan over the built site in headless Edge.
 * Usage: node scripts/a11y.mjs  (serves dist/ on :8933) */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import puppeteer from "puppeteer-core";

const DIST = new URL("../dist", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/json", ".svg": "image/svg+xml",
  ".png": "image/png", ".wasm": "application/wasm" };
const server = createServer(async (req, res) => {
  let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (path.endsWith("/")) path += "index.html";
  try {
    const data = await readFile(join(DIST, path));
    res.writeHead(200, { "Content-Type": TYPES[extname(path)] ?? "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(8933, "127.0.0.1", r));

const PAGES = [
  "/", "/bills/", "/bills/2025/", "/bills/2025/ab656/", "/bills/2025/ab1/",
  "/bills/2025/sb23/", "/votes/2025-av0001-ar1/", "/legislators/",
  "/hearing-none/", "/hearing-none/2025/", "/hearings/", "/calendar/",
  "/my-reps/", "/elections/2026/", "/data/", "/about/", "/money/",
];

const axeSource = await readFile(
  new URL("../node_modules/axe-core/axe.min.js", import.meta.url), "utf-8",
);
const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: true,
});
const page = await browser.newPage();
// include one legislator page with full cards
const legIndex = await readFile(join(DIST, "legislators/index.html"), "utf-8").catch(() => "");
const legMatch = legIndex.match(/href="(\/legislators\/[^"]+\/)"/);
if (legMatch) PAGES.push(legMatch[1]);

let totalViolations = 0;
const summary = new Map();
for (const path of PAGES) {
  await page.goto(`http://127.0.0.1:8933${path}`, { waitUntil: "networkidle2", timeout: 30000 });
  await page.evaluate(axeSource);
  const results = await page.evaluate(() =>
    axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"] }),
  );
  for (const v of results.violations) {
    totalViolations += v.nodes.length;
    const key = `${v.impact ?? "minor"} | ${v.id} | ${v.help}`;
    const entry = summary.get(key) ?? { count: 0, pages: new Set(), sample: "" };
    entry.count += v.nodes.length;
    entry.pages.add(path);
    entry.sample ||= (v.nodes[0]?.html ?? "").slice(0, 110);
    summary.set(key, entry);
  }
  console.log(`${path}: ${results.violations.length ? results.violations.map((v) => `${v.id}(${v.nodes.length})`).join(", ") : "clean"}`);
}
console.log(`\n=== ${totalViolations} violation nodes across ${PAGES.length} pages ===`);
for (const [key, e] of [...summary.entries()].sort()) {
  console.log(`\n${key}\n  nodes: ${e.count} on ${[...e.pages].slice(0, 4).join(" ")}\n  e.g.: ${e.sample}`);
}
await browser.close();
server.close();
process.exit(totalViolations ? 1 : 0);
