import assert from "node:assert/strict";
import { serveDist, launchBrowser } from "./lib/serve.mjs";
import { gotoLayoutReady, waitForNoSearchResults } from "./lib/readiness.mjs";

const server = await serveDist(8938);
const browser = await launchBrowser();
const page = await browser.newPage();
const errors = [];
page.on("pageerror", error => errors.push(error.message));
const origin = "http://127.0.0.1:8938";

try {
  await page.setViewport({ width: 390, height: 844 });
  await gotoLayoutReady(page, origin);
  await page.type("#q", "child care");
  await page.click('#search-form button[type="submit"]');
  await page.waitForSelector("#search-results > a", { timeout: 30000 });
  assert.equal(new URL(page.url()).searchParams.get("q"), "child care", "search query is shareable");
  const before = await page.$$eval("#search-results > a", links => links.length);
  await page.click("#search-more");
  await page.waitForFunction(n => document.querySelectorAll("#search-results > a").length > n, {}, before);
  await page.focus("#q");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector("#search-status")?.textContent.includes("matches shown"));
  assert.equal(new URL(page.url()).pathname, "/", "Enter does not open an arbitrary result");
  await page.click('[data-type-chip="Bill|Resolution"]');
  await page.waitForFunction(() => new URL(location.href).searchParams.get("type") === "Bill|Resolution");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("#search-results > a", { timeout: 30000 });
  assert.equal(await page.$eval("#q", el => el.value), "child care");
  assert.equal(await page.$eval('[data-type-chip="Bill|Resolution"]', el => el.getAttribute("aria-pressed")), "true");
  await page.goto(origin + "/following/", { waitUntil: "domcontentloaded" });
  await page.goBack({ waitUntil: "domcontentloaded" });
  assert.equal(await page.$eval("#q", el => el.value), "child care", "Back preserves the search");

  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewport({ width, height: 900 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `search filters fit at ${width}px`);
  }
  await page.click("#search-clear");
  assert.equal(new URL(page.url()).searchParams.has("type"), false);
  await page.$eval("#q", el => { el.value = ""; });
  await page.type("#q", "zzzznonexistentrecordzzzz");
  await waitForNoSearchResults(page, "zzzznonexistentrecordzzzz");
  assert.equal(await page.$$eval("#search-results > a", links => links.length), 0);

  await gotoLayoutReady(page, origin + "/bills/2025/?q=gun%20safes");
  assert.equal(await page.$eval("#bill-filter", el => el.value), "gun safes");
  assert.ok(await page.$$eval("[data-bill-row].sorted-hidden", rows => rows.length) > 0);
  await page.click('[data-filter-clear="bill-filter"]');
  assert.equal(new URL(page.url()).searchParams.has("q"), false);
  assert.equal(await page.$$eval("[data-bill-row].sorted-hidden", rows => rows.length), 0);

  for (const [path, selector] of [["/", "#home-addr"], ["/my-reps/", "#addr"]]) {
    await page.setViewport({ width: 390, height: 844 });
    await gotoLayoutReady(page, origin + path);
    assert.ok(await page.$eval(selector, el => el.getBoundingClientRect().width) >= 250, `${path} address has typing room`);
  }
  await page.setViewport({ width: 320, height: 900 });
  await page.evaluate(() => { document.documentElement.style.fontSize = "125%"; });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "enlarged header fits at 320px");
  await page.click("header [data-nav-menu] > summary");
  assert.ok(await page.$eval("header [data-nav-menu] > div", el => {
    const rect = el.getBoundingClientRect();
    return rect.left >= 0 && rect.right <= innerWidth;
  }), "expanded menu stays inside the narrow viewport");
  assert.deepEqual(errors, [], "no browser script errors");
  console.log("UX checks passed: search pagination, shareable filters, empty state, narrow forms and reflow.");
} catch (error) {
  console.error(await page.evaluate(() => ({ url: location.href, query: document.querySelector("#q")?.value, status: document.querySelector("#search-status")?.textContent })));
  console.error(errors);
  throw error;
} finally {
  await browser.close();
  server.close();
}
