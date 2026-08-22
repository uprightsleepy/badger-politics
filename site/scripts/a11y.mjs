/** axe-core accessibility scan over the built site in headless Edge.
 * Usage: node scripts/a11y.mjs  (serves dist/ on :8933) */
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import {
  DIST, serveDist, launchBrowser, firstLegislatorHref, moneyLegislatorHref,
} from "./lib/serve.mjs";

const server = await serveDist(8933);

const PAGES = [
  "/", "/bills/", "/bills/2025/", "/bills/2025/ab656/", "/bills/2025/ab1/",
  "/bills/2025/sb23/", "/votes/2025-av0001-ar1/", "/legislators/",
  "/hearing-none/", "/hearing-none/2025/", "/calendar/",
  "/my-reps/", "/elections/2026/", "/data/", "/about/", "/money/", "/404.html",
  "/money/committees/", "/money/committees/651839/", "/committees/", "/subjects/",
  "/following/",
];
{
  const idx = await readFile(join(DIST, "subjects/index.html"), "utf-8").catch(() => "");
  const m = idx.match(/href="(\/subjects\/[^"]+\/)"/);
  if (m) PAGES.push(m[1]);
}
{
  const idx = await readFile(join(DIST, "committees/index.html"), "utf-8").catch(() => "");
  const m = idx.match(/href="(\/committees\/[^"]+\/)"/);
  if (m) PAGES.push(m[1]);
}

const axeSource = await readFile(
  new URL("../node_modules/axe-core/axe.min.js", import.meta.url), "utf-8",
);
const browser = await launchBrowser();
const page = await browser.newPage();
// include one legislator page with full cards, and one whose money card
// carries the timeline chart (coverage differs between the two)
const legHref = await firstLegislatorHref();
if (legHref) PAGES.push(legHref);
const moneyHref = await moneyLegislatorHref();
if (moneyHref) PAGES.push(moneyHref);

// phone width catches target-size and hidden-metadata issues that the
// desktop pass structurally cannot see
const VIEWPORTS = [
  { label: "desktop", width: 1280, height: 800 },
  { label: "mobile", width: 360, height: 740 },
];
let totalViolations = 0;
const summary = new Map();
for (const vp of VIEWPORTS) {
  await page.setViewport({ width: vp.width, height: vp.height });
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
      entry.pages.add(`${path}@${vp.label}`);
      entry.sample ||= (v.nodes[0]?.html ?? "").slice(0, 110);
      summary.set(key, entry);
    }
    console.log(`${path} @${vp.label}: ${results.violations.length ? results.violations.map((v) => `${v.id}(${v.nodes.length})`).join(", ") : "clean"}`);
  }
}
console.log(`\n=== ${totalViolations} violation nodes across ${PAGES.length} pages x ${VIEWPORTS.length} viewports ===`);
for (const [key, e] of [...summary.entries()].sort()) {
  console.log(`\n${key}\n  nodes: ${e.count} on ${[...e.pages].slice(0, 4).join(" ")}\n  e.g.: ${e.sample}`);
}
await browser.close();
server.close();
process.exit(totalViolations ? 1 : 0);
