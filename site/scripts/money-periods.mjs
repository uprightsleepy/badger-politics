/** Funding defaults, linked periods, history navigation, and mobile layout. */
import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { serveDist, launchBrowser, blockThirdPartyAssets } from "./lib/serve.mjs";
import { gotoLayoutReady } from "./lib/readiness.mjs";

const server = process.env.BASE_URL ? null : await serveDist(8937);
const base = process.env.BASE_URL ?? "http://127.0.0.1:8937";
const db = new Database(process.env.WI_DATABASE_PATH ?? fileURLToPath(new URL("../../data/wi.sqlite", import.meta.url)), { readonly: true });
const browser = await launchBrowser();
const page = await browser.newPage();
await blockThirdPartyAssets(page);
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const dollar = (v) => "$" + Math.round(v).toLocaleString("en-US");
const year = Number(new Intl.DateTimeFormat("en-US", {year:"numeric",timeZone:"America/Chicago"}).format(new Date()));
const current = String(year + year % 2);
const previous = String(Number(current) - 2);
const scopes = ["all", "office"];
const periodSelector = "[data-money-period-select]";
const visible = (scope) => `[data-money-period]:not([hidden])[data-money-scope="${scope}"]`;
const inTerm = "EXISTS (SELECT 1 FROM person_terms t WHERE t.person_id=c.person_id AND c.date>=t.start AND c.date<=COALESCE(t.end,'9999-12-31'))";
const expected = (period, scope, person = null) => db.prepare(`SELECT COALESCE(SUM(amount),0) AS total FROM contributions c
  WHERE date BETWEEN ? AND ? ${scope === "office" ? "AND " + inTerm : ""} ${person ? "AND person_id=?" : ""}`)
  .get(...[period === "all" ? "0000" : `${Number(period)-1}-01-01`, period === "all" ? "9999" : `${period}-12-31`, ...(person ? [person] : [])]).total;
const choose = async (period, scope = "all") => {
  await page.select(periodSelector, period);
  await page.evaluate((checked) => {
    const box = document.querySelector("[data-money-office]");
    if (box && box.checked !== checked) { box.checked = checked; box.dispatchEvent(new Event("change", {bubbles:true})); }
  }, scope === "office");
  await page.waitForSelector(visible(scope), { timeout: 30000 }); // fragments load on demand
};
const assertLayout = async () => {
  assert.ok(await page.evaluate(() => Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)<=innerWidth+1), "Horizontal overflow");
};
try {
  for (const width of [320, 360, 768, 1280]) {
    await page.setViewport({ width, height: 900 });
    await gotoLayoutReady(page, base + "/money/", {timeout:120000});
    assert.equal(await page.$eval(periodSelector, (e) => e.value), current);
    for (const period of [current, previous, "all"]) {
      for (const scope of scopes) {
        await choose(period, scope);
        const text = await page.$eval(visible(scope), (e)=>e.innerText);
        assert.ok(text.includes(dollar(expected(period,scope))), `Overview ${period}/${scope} amount`);
        assert.ok(text.includes("reported receipts"));
        await assertLayout();
      }
    }
    console.log(`${width}px: all funding selections fit and agree with SQLite`);
  }
  const linkedPeriod = expected(previous, "office") ? previous : "all";
  await choose(linkedPeriod, "office");
  const link = await page.$eval(`${visible("office")} a[href^="/legislators/"]`, (a)=>a.getAttribute("href"));
  assert.ok(link.includes(`period=${linkedPeriod}`) && link.includes("scope=office"));
  await gotoLayoutReady(page, base + link, {timeout:120000});
  assert.equal(await page.$eval(periodSelector,(e)=>e.value),linkedPeriod);
  assert.equal(await page.$eval("[data-money-office]",(e)=>e.checked),true);
  const slugs = JSON.parse(await readFile(new URL("../src/data/person-slugs.json",import.meta.url),"utf8"));
  const slug = new URL(base+link).pathname.split("/")[2];
  const person = Object.entries(slugs).find(([,value])=>value===slug)?.[0]
    ?? db.prepare("SELECT id FROM people WHERE id LIKE ?").get(`%/${slug}`)?.id;
  assert.ok(person,"Profile source identity");
  for (const period of [previous,current,"all"]) {
    await choose(period);
    const text = await page.$eval(visible("all"),(e)=>e.innerText);
    const total = expected(period,"all",person);
    assert.ok(text.includes(dollar(total)) || (total === 0 && text.includes("No receipts collected")));
  }
  await page.goBack({waitUntil:"domcontentloaded"});
  assert.equal(await page.$eval(periodSelector,(e)=>e.value),current,"Back restores previous selection");
  await gotoLayoutReady(page,base+`/money/committees/?period=${linkedPeriod}&scope=office`,{timeout:120000});
  await page.waitForFunction(()=>document.querySelector("#committee-filter-status")?.textContent);
  assert.equal(await page.$eval(periodSelector,(e)=>e.value),linkedPeriod);
  const donorLink = await page.$eval(`${visible("office")} a[href^="/money/committees/"]`,(a)=>a.getAttribute("href"));
  assert.ok(donorLink.includes(`period=${linkedPeriod}`));
  await gotoLayoutReady(page,base+donorLink,{timeout:120000});
  assert.equal(await page.$eval(periodSelector,(e)=>e.value),linkedPeriod);
  await choose("all");
  await assertLayout();
  await gotoLayoutReady(page,base+"/money/?period=invalid&scope=invalid",{timeout:120000});
  assert.equal(await page.$eval(periodSelector,(e)=>e.value),current);
  assert.equal(await page.$eval("[data-money-office]",(e)=>e.checked),false);
  assert.deepEqual(errors,[]);
  if (process.env.SHOTS_DIR) {
    await mkdir(process.env.SHOTS_DIR,{recursive:true});
    for (const width of [360,1280]) {
      await page.setViewport({width,height:1000});
      await page.screenshot({path:`${process.env.SHOTS_DIR}/money-${width}.png`});
    }
  }
  console.log("Funding navigation, shareable selections, browser Back, defaults, and period totals passed.");
} finally {
  await browser.close();
  server?.close();
  db.close();
}
