/** Does the Content-Security-Policy break anything on a deployed site?
 *
 * Run against a released URL, not a local build: Firebase serves these
 * headers, so nothing local exercises them. A CSP failure is invisible to
 * a visitor — search silently returns nothing, the address lookup silently
 * stops — so this listens for the browser's own securitypolicyviolation
 * events and drives the two paths most likely to break: the Census
 * geocoder, which injects a script from a third host, and Pagefind, which
 * compiles WebAssembly.
 *
 * Usage: node scripts/csp.mjs https://badgerpolitics-dev.web.app
 */
import { launchBrowser } from "./lib/serve.mjs";

const BASE = process.argv[2] ?? "https://badgerpolitics-dev.web.app";
const browser = await launchBrowser();
const page = await browser.newPage();

const violations = [];
const pageErrors = [];
page.on("console", (m) => {
  const t = m.text();
  if (/Content Security Policy|Refused to/i.test(t)) violations.push(t.slice(0, 200));
});
page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 160)));

// the browser fires this for every blocked resource, including ones a
// console listener can miss
await page.evaluateOnNewDocument(() => {
  window.__cspViolations = [];
  document.addEventListener("securitypolicyviolation", (e) => {
    window.__cspViolations.push(`${e.violatedDirective} blocked ${e.blockedURI}`);
  });
});

const check = async (path, after) => {
  violations.length = 0;
  pageErrors.length = 0;
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle2", timeout: 45000 });
  if (after) await after();
  const fromEvents = await page.evaluate(() => window.__cspViolations ?? []);
  const all = [...new Set([...violations, ...fromEvents])];
  const ok = all.length === 0 && pageErrors.length === 0;
  console.log(`${ok ? "PASS" : "FAIL"}: ${path}`);
  for (const v of all) console.log(`    CSP: ${v}`);
  for (const e of pageErrors) console.log(`    JS:  ${e}`);
  return ok;
};

let bad = 0;

// headers actually served
const res = await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
const h = res.headers();
console.log("--- response headers ---");
for (const k of [
  "content-security-policy",
  "x-content-type-options",
  "referrer-policy",
  "permissions-policy",
  "strict-transport-security",
]) {
  const v = h[k];
  console.log(`  ${k}: ${v ? v.slice(0, 90) + (v.length > 90 ? "…" : "") : "MISSING"}`);
  if (!v) bad++;
}
console.log("--- pages ---");

for (const p of ["/", "/bills/2025/", "/legislators/", "/money/", "/calendar/"]) {
  if (!(await check(p))) bad++;
}

// the two things the CSP could plausibly break
if (
  !(await check("/my-reps/", async () => {
    // exercises the Census JSONP path: it appends a script to a third host
    await page.type("#addr", "7120 W National Ave, West Allis, WI");
    await page.click("#addr-form button[type=submit]");
    await page.waitForFunction(
      () => /District|didn't|Couldn't|doesn't/i.test(document.getElementById("status")?.textContent ?? ""),
      { timeout: 30000 },
    ).catch(() => {});
    console.log(
      "    geocoder said:",
      (await page.$eval("#status", (el) => el.textContent.trim())).slice(0, 90),
    );
  }))
) bad++;

// search must still load its wasm/index
if (
  !(await check("/", async () => {
    await page.type("#q", "vos").catch(() => {});
    await new Promise((r) => setTimeout(r, 2500));
  }))
) bad++;

await browser.close();
console.log(bad === 0 ? "\nCSP OK" : `\n${bad} PROBLEM(S)`);
process.exit(bad === 0 ? 0 : 1);
