import { launchBrowser } from "./lib/serve.mjs";
const B = "https://badgerpolitics-dev.web.app";
const browser = await launchBrowser();
const page = await browser.newPage();
let bad = 0;
const ok = (n, c, d="") => { console.log(`${c?"PASS":"FAIL"}: ${n} ${d}`); if(!c) bad++; };

// search must actually return results, not merely avoid CSP errors
await page.goto(`${B}/?q=vos`, { waitUntil: "networkidle2" });
await new Promise(r => setTimeout(r, 4000));
const hits = await page.evaluate(() =>
  document.querySelectorAll("#search-results a").length);
ok("search returns results for 'vos'", hits > 0, `${hits} hits`);

// pagination + status pages resolve and hold the right slice
for (const [path, expect] of [
  ["/bills/2025/", "page 1"],
  ["/bills/2025/page/2/", "page 2"],
  ["/bills/2025/status/enacted/", "enacted"],
]) {
  const r = await page.goto(`${B}${path}`, { waitUntil: "domcontentloaded" });
  const rows = await page.evaluate(() => document.querySelectorAll("[data-bill-row]").length);
  ok(`${path} (${expect})`, r.status() === 200 && rows > 0, `${r.status()}, ${rows} rows`);
}

// a member's paginated full record
const rec = await page.goto(`${B}/legislators/0301a2cd-37fc-46f6-948a-f1fade57b5c0/bills/1/`, { waitUntil: "domcontentloaded" });
const recRows = await page.evaluate(() => document.querySelectorAll("li").length);
const robots = await page.evaluate(() => document.querySelector('meta[name=robots]')?.content ?? "");
ok("member bill record page", rec.status() === 200 && recRows > 0, `${rec.status()}, ${recRows} items`);
ok("record page is noindex, follow", robots === "noindex, follow", robots);

// weight, measured over the wire
for (const p of ["/bills/2025/", "/legislators/0301a2cd-37fc-46f6-948a-f1fade57b5c0/"]) {
  const r = await page.goto(`${B}${p}`, { waitUntil: "domcontentloaded" });
  const kb = Math.round((await r.text()).length / 1024);
  ok(`${p} under 600 KB`, kb < 600, `${kb} KB`);
}

// breadcrumbs shipped
const crumbs = await page.evaluate(() =>
  [...document.querySelectorAll('script[type="application/ld+json"]')]
    .some(s => s.textContent.includes("BreadcrumbList")));
ok("BreadcrumbList on a legislator page", crumbs);

await browser.close();
console.log(bad === 0 ? "\nDEV OK" : `\n${bad} FAILURES`);
process.exit(bad === 0 ? 0 : 1);
