import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { launchBrowser } from "../lib/serve.mjs";
import { gotoLayoutReady, waitForNoSearchResults } from "../lib/readiness.mjs";

let server, browser, base;
const html = (body) => `<!doctype html><html lang="en"><head><title>Harness fixture</title></head><body>${body}</body></html>`;
const calendar = '<h2 id="month-label">Loading calendar…</h2><div id="grid"></div><section id="day-panel" class="hidden"></section>';
const calendarReady = `document.getElementById('month-label').textContent='September 2026';
  document.getElementById('grid').innerHTML='<div>Day</div>'.repeat(30);
  document.getElementById('day-panel').classList.remove('hidden');`;

before(async () => {
  server = createServer((req, res) => {
    const { pathname, searchParams } = new URL(req.url, "http://fixture");
    res.setHeader("Cache-Control", "no-store");
    if (pathname === "/slow.css") {
      setTimeout(() => res.writeHead(200, { "Content-Type": "text/css" }).end("#wide { width: 2000px; }"), 150);
      return;
    }
    if (pathname === "/module.js") {
      setTimeout(() => res.writeHead(200, { "Content-Type": "text/javascript" }).end("document.body.dataset.initialized = 'yes';"), 150);
      return;
    }
    if (pathname === "/delayed-data") {
      setTimeout(() => res.writeHead(200, { "Content-Type": "application/json" }).end("{}"), 150);
      return;
    }
    if (pathname === "/slow.svg") {
      setTimeout(() => res.writeHead(200, { "Content-Type": "image/svg+xml" })
        .end('<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="50"></svg>'), 200);
      return;
    }
    let body;
    switch (pathname) {
      case "/styled/":
        body = '<link rel="stylesheet" href="/slow.css"><main id="wide">Overflow</main><script type="module" src="/module.js"></script>';
        break;
      case "/broken-style/":
        body = '<link rel="stylesheet" href="/missing.css"><main>Unstyled</main>';
        break;
      case "/image/":
        body = '<main><img src="/slow.svg" alt="Wide fixture"></main>';
        break;
      case "/lazy-image/":
        body = '<main><img src="/slow.svg" loading="lazy" alt=""></main>';
        break;
      case "/broken-image/":
        body = '<main><img src="/missing.svg" alt="Missing fixture"></main>';
        break;
      case "/calendar/":
        body = calendar;
        if (!searchParams.has("stuck")) body += `<script>fetch('/delayed-data').then(() => { ${calendarReady} });</script>`;
        break;
      case "/following/":
        body = '<p id="follow-status"></p>';
        if (!searchParams.has("stuck")) body += "<script>fetch('/delayed-data').then(() => document.getElementById('follow-status').textContent='0 followed items loaded.');</script>";
        break;
      case "/search/":
        body = '<input id="q" value="pedophiles"><p id="search-status"></p><div id="search-results"></div>';
        break;
      case "/a11y/":
        body = '<main><button></button></main>';
        break;
      default:
        res.writeHead(404).end("missing");
        return;
    }
    res.writeHead(200, { "Content-Type": "text/html" }).end(html(body));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await launchBrowser();
});
after(async () => {
  await browser?.close();
  if (server) {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});

const withPage = async (t) => {
  const page = await browser.newPage();
  t.after(() => page.close());
  return page;
};

test("readiness waits for styles and module initialization; overflow is still detectable", async (t) => {
  const page = await withPage(t);
  await page.setViewport({ width: 344, height: 900 });
  await gotoLayoutReady(page, `${base}/styled/`);
  assert.equal(await page.evaluate(() => document.body.dataset.initialized), "yes");
  assert.equal(await page.$eval("#wide", (el) => el.getBoundingClientRect().width), 2000);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth));
});

test("missing pages and styles fail instead of producing a clean layout result", async (t) => {
  const page = await withPage(t);
  await assert.rejects(gotoLayoutReady(page, `${base}/missing/`), /Layout navigation failed/);
  await assert.rejects(gotoLayoutReady(page, `${base}/broken-style/`, { timeout: 300 }), /Required layout resources failed|Waiting failed/);
});

test("calendar waits for async rendering, including months with no event buttons", async (t) => {
  const page = await withPage(t);
  await gotoLayoutReady(page, `${base}/calendar/`);
  assert.equal(await page.$$eval("#grid > div", (els) => els.length), 30);
  await assert.rejects(gotoLayoutReady(page, `${base}/calendar/?stuck`, { timeout: 300 }), /Waiting failed/);
});

test("local images settle before layout measurement and broken images fail", async (t) => {
  const page = await withPage(t);
  await page.setViewport({ width: 344, height: 900 });
  await gotoLayoutReady(page, `${base}/image/`);
  assert.equal(await page.$eval("img", (img) => img.naturalWidth), 2000);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth));
  await gotoLayoutReady(page, `${base}/lazy-image/`);
  assert.equal(await page.$eval("img", (img) => img.naturalWidth), 2000);
  await assert.rejects(gotoLayoutReady(page, `${base}/broken-image/`), /Required layout images failed/);
});

test("following waits for the completed empty state and rejects stuck content", async (t) => {
  const page = await withPage(t);
  await gotoLayoutReady(page, `${base}/following/`);
  assert.equal(await page.$eval("#follow-status", (el) => el.textContent), "0 followed items loaded.");
  await assert.rejects(gotoLayoutReady(page, `${base}/following/?stuck`, { timeout: 300 }), /Waiting failed/);
});

test("axe still detects a broken accessible name after the faster navigation", async (t) => {
  const page = await withPage(t);
  await gotoLayoutReady(page, `${base}/a11y/`);
  const axe = await readFile(new URL("../../node_modules/axe-core/axe.min.js", import.meta.url), "utf-8");
  await page.evaluate(axe);
  const result = await page.evaluate(() => axe.run(document, { runOnly: ["button-name"] }));
  assert.ok(result.violations.some((v) => v.id === "button-name"));
});

test("no-results assertion rejects empty, stale, hidden, and junk-result states", async (t) => {
  const page = await withPage(t);
  await page.goto(`${base}/search/`);
  const wait = () => waitForNoSearchResults(page, "pedophiles", { timeout: 200 });
  await assert.rejects(wait(), /Waiting failed/);
  await page.evaluate(() => {
    document.getElementById("search-status").textContent = "No results.";
    document.getElementById("search-results").textContent = 'Nothing matches “previous query”';
  });
  await assert.rejects(wait(), /Waiting failed/);
  await page.evaluate(() => {
    const box = document.getElementById("search-results");
    box.textContent = 'Nothing matches “pedophiles”';
    box.classList.add("hidden");
  });
  await assert.rejects(wait(), /Waiting failed/);
  await page.evaluate(() => {
    const box = document.getElementById("search-results");
    box.classList.remove("hidden");
    box.insertAdjacentHTML("beforeend", '<a href="/junk/">Junk result</a>');
  });
  await assert.rejects(wait(), /Waiting failed/);
  await page.evaluate(() => {
    const box = document.getElementById("search-results");
    box.querySelector("a").remove();
    box.insertAdjacentHTML("beforeend", '<p><a href="/my-reps/">Recovery link</a></p>');
  });
  await wait();
});

test("search rejects short prefix fallbacks but keeps genuine stems and exact words", async () => {
  const source = await readFile(new URL("../../src/pages/index.astro", import.meta.url), "utf-8");
  const filterSource = source.slice(source.indexOf("const resultFilter ="), source.indexOf("// Recent searches"));
  const resultFilter = new Function(`${filterSource}; return resultFilter;`)();
  const makeResult = (id, excerpt) => ({ id, data: async () => ({ url: `/${id}/`, excerpt }) });
  const filters = { type: "City Council" };
  const calls = [];
  const pagefind = {
    search: async (query, options) => {
      calls.push(query);
      assert.deepEqual(options, { filters });
      const ids = { '"taxes"': ["tax"], '"running"': ["run"], '"pedophiles"': [] }[query];
      assert.ok(ids, `unexpected exact query ${query}`);
      return { results: ids.map((id) => ({ id })) };
    },
  };
  const missing = resultFilter("pedophiles", pagefind, filters);
  assert.equal(await missing(makeResult("initial", "<mark>P.</mark>")), null);
  assert.equal(await missing(makeResult("acronym", "<mark>PEOs</mark>")), null);
  const bridges = await Promise.all([
    missing(makeResult("bridge", "A <mark>Ped</mark> Bridge project")),
    missing(makeResult("other", "Another <mark>Ped</mark> Bridge project")),
  ]);
  assert.deepEqual(bridges, [null, null]);
  assert.deepEqual(calls, ['"pedophiles"']);
  assert.ok(await missing(makeResult("real", "A record discussing <mark>pedophiles</mark>")));

  assert.ok(await resultFilter("taxes", pagefind, filters)(makeResult("tax", "<mark>tax</mark>")));
  assert.ok(await resultFilter("running", pagefind, filters)(makeResult("run", "<mark>run</mark>")));
  assert.ok(await resultFilter("running taxes", pagefind, filters)(makeResult("tax", "<mark>tax</mark>")));
  assert.ok(await resultFilter("tax", pagefind, filters)(makeResult("tax", "<mark>tax</mark>")));
  assert.ok(await resultFilter("marriage", pagefind, filters)(makeResult("marriage", "<mark>marriage</mark>")));
});
