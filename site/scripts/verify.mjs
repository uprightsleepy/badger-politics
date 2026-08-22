/** Phase 5 acceptance verification: drives the built site in headless Edge.
 * Usage: node scripts/verify.mjs  (serves dist/ itself on :8931) */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import puppeteer from "puppeteer-core";

const DIST = new URL("../dist", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/json", ".svg": "image/svg+xml",
  ".wasm": "application/wasm", ".pf_meta": "application/octet-stream",
  ".pf_index": "application/octet-stream", ".pf_fragment": "application/octet-stream" };

const server = createServer(async (req, res) => {
  let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
  if (path.endsWith("/")) path += "index.html";
  try {
    const data = await readFile(join(DIST, path));
    res.writeHead(200, { "Content-Type": TYPES[extname(path)] ?? "application/octet-stream" });
    res.end(data);
  } catch {
    res.writeHead(404).end("nope");
  }
});
await new Promise((r) => server.listen(8931, "127.0.0.1", r));

const browser = await puppeteer.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: true,
});
const page = await browser.newPage();
const results = [];
const check = (name, ok, detail = "") =>
  results.push({ name, ok, detail }) && console.log(`${ok ? "PASS" : "FAIL"}: ${name} ${detail}`);

// track whether the GoatCounter script is requested
let goatRequested = false;
page.on("request", (r) => {
  if (r.url().includes("goatcounter") || r.url().includes("gc.zgo.at")) goatRequested = true;
});

// 1. search: "child marriage" -> AB 656
await page.goto("http://127.0.0.1:8931/", { waitUntil: "networkidle2" });
await page.waitForSelector("#q", { timeout: 10000 });
await page.type("#q", "child marriage");
await page.waitForSelector("#search-results a", { timeout: 10000 });
await new Promise((r) => setTimeout(r, 800));
const hits = await page.$$eval("#search-results a", (as) =>
  as.slice(0, 5).map((a) => ({ text: a.textContent.trim(), href: a.getAttribute("href") })),
);
check(
  "search 'child marriage' surfaces AB 656",
  hits.some((h) => h.href?.includes("/bills/2025/ab656")),
  JSON.stringify(hits.map((h) => h.text?.slice(0, 30))),
);

// 1b. degenerate query must NOT dredge up initial-letter matches. Wait
// for THIS query's outcome (the no-match message), not leftover results
// from the previous search; the assertion itself is unchanged.
await page.$eval("#q", (el) => (el.value = ""));
await page.type("#q", "pedophiles");
await page.waitForFunction(
  () => document.getElementById("search-results").textContent.includes("No bills match"),
  { timeout: 10000 },
).catch(() => {});
const degenerateLinks = await page.$$eval("#search-results a", (as) => as.length);
check("search 'pedophiles' returns no junk matches", degenerateLinks === 0, `${degenerateLinks} links`);

// 2. my-reps: West Allis address -> AD 14 (Tenorio) + SD 5 (Hutton)
await page.goto("http://127.0.0.1:8931/my-reps/", { waitUntil: "networkidle2" });
await page.type("#addr", "7120 W National Ave, West Allis, WI");
await page.click("#addr-form button[type=submit]");
await page.waitForFunction(
  () => !document.getElementById("result").classList.contains("hidden"),
  { timeout: 30000 },
);
const repsText = await page.$eval("#reps", (el) => el.textContent);
check("West Allis -> Assembly D14 Tenorio", repsText.includes("Angelito Tenorio"), "");
check("West Allis -> Senate D5 Hutton", repsText.includes("Rob Hutton"), "");
const savedDistrict = await page.evaluate(() => localStorage.getItem("bp-district"));
check("district saved to localStorage", savedDistrict === '{"ad":14,"sd":5}', savedDistrict);

// 3. pinning on a bill with a floor vote (AB 656 died unheard - it has no votes)
await page.goto("http://127.0.0.1:8931/bills/2025/ab1/", { waitUntil: "networkidle2" });
await new Promise((r) => setTimeout(r, 300));
const pinned = await page.$$eval("[data-your-reps-note]:not(.hidden)", (els) =>
  els.map((el) => el.textContent.trim()),
);
check(
  "AB 1 roll calls pin the saved district's reps",
  pinned.length >= 1,
  JSON.stringify(pinned),
);

// 3b. saved reps are highlighted anywhere they appear (legislators index)
await page.goto("http://127.0.0.1:8931/legislators/", { waitUntil: "networkidle2" });
await page.waitForFunction(
  () => [...document.querySelectorAll("a")].some((a) => a.classList.contains("bg-gold-100")),
  { timeout: 10000 },
).catch(() => {});
const highlighted = await page.$$eval("a.bg-gold-100", (as) => as.map((a) => a.textContent.trim()));
check(
  "saved reps highlighted on legislators index",
  highlighted.some((t) => t.includes("Tenorio")) && highlighted.some((t) => t.includes("Hutton")),
  JSON.stringify(highlighted.slice(0, 4)),
);

// 4. AB 656 page shows Hearing None banner + LRB analysis
await page.goto("http://127.0.0.1:8931/bills/2025/ab656/", { waitUntil: "networkidle2" });
const body = await page.$eval("body", (el) => el.textContent);
check("AB 656 shows Hearing None banner", body.includes("died at the end of the session without ever receiving"));
check("AB 656 leads with LRB analysis", body.includes("marriageable age"));
check("footer carries independence disclaimer", body.includes("independent project, not affiliated with the State of Wisconsin"));
check("GoatCounter script requested", goatRequested, "");

await browser.close();
server.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
