/** Phase 5 acceptance verification: drives the built site in headless Edge.
 * Usage: node scripts/verify.mjs  (serves dist/ itself on :8931) */
import { serveDist, launchBrowser } from "./lib/serve.mjs";

const server = await serveDist(8931);

const browser = await launchBrowser();
const page = await browser.newPage();
const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}: ${name} ${detail}`);
};

// track whether the GoatCounter script is requested
let goatRequested = false;
page.on("request", (r) => {
  if (r.url().includes("goatcounter") || r.url().includes("gc.zgo.at")) goatRequested = true;
});

// 1. search: "child marriage" -> AB 656
// 30s, not 10: the first search loads Pagefind's WASM and index shards for
// 23,000 pages. That is comfortable locally and marginal on a loaded CI
// runner, where it timed out and read as a broken search.
await page.goto("http://127.0.0.1:8931/", { waitUntil: "networkidle2" });
await page.waitForSelector("#q", { timeout: 30000 });
await page.type("#q", "child marriage");
await page.waitForSelector("#search-results a", { timeout: 30000 });
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
  () => document.getElementById("search-results").textContent.includes("Nothing matches"),
  { timeout: 30000 },
).catch(() => {});
// direct children only: the no-result state deliberately offers recovery
// links (find-my-legislators, official record) inside a nested block, and
// those are not junk matches
const degenerateLinks = await page.$$eval("#search-results > a", (as) => as.length);
check("search 'pedophiles' returns no junk matches", degenerateLinks === 0, `${degenerateLinks} links`);

// 2. my-reps: West Allis address -> AD 14 (Tenorio) + SD 5 (Hutton)
await page.goto("http://127.0.0.1:8931/my-reps/", { waitUntil: "networkidle2" });
await page.type("#addr", "7120 W National Ave, West Allis, WI");
await page.click("#addr-form button[type=submit]");
await page.waitForFunction(
  () => !document.getElementById("result").classList.contains("hidden"),
  { timeout: 60000 },
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
// domcontentloaded, not networkidle2: this page loads 131 member
// portraits from third-party hosts and the check below reads the DOM.
await page.goto("http://127.0.0.1:8931/legislators/", { waitUntil: "domcontentloaded" });
await page.waitForFunction(
  () => [...document.querySelectorAll("a")].some((a) => a.classList.contains("bg-gold-100")),
  { timeout: 30000 },
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
