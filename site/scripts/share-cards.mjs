/** Render the share cards the build listed in dist/og/cards.json
 * (src/lib/share.ts) to PNGs at their own paths, then delete the manifest.
 * Runs between `astro build` and Pagefind:
 * `BROWSER_PATH=... node scripts/share-cards.mjs`.
 *
 * Same browser, fonts and mark as the sitewide card (make-og.mjs). Each tab
 * loads the template once and only the text changes per card, so a card
 * costs one screenshot. */
import { mkdir, readFile, rm } from "node:fs/promises";
import { availableParallelism } from "node:os";
import { dirname, join } from "node:path";
import { cardPage, cardTab, mark, shoot } from "./lib/og.mjs";
import { DIST, launchBrowser } from "./lib/serve.mjs";

const manifest = join(DIST, "og", "cards.json");
const cards = JSON.parse(await readFile(manifest, "utf-8"));

const html = await cardPage(`
.brand { position: absolute; left: 80px; top: 60px; display: flex; align-items: center; gap: 18px; font: 800 36px/1 Overpass, sans-serif; }
.brand svg { width: 54px; height: auto; display: block; }
.copy { position: absolute; left: 80px; right: 80px; top: 150px; bottom: 156px; display: flex; flex-direction: column; justify-content: center; }
#kicker { font: 700 30px/1.25 Overpass, sans-serif; color: #55605A; margin: 0 0 18px; }
#title { font: 800 66px/1.1 Overpass, sans-serif; letter-spacing: -0.01em; margin: 0;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; }
#title.long { font-size: 54px; }
.foot { position: absolute; left: 80px; right: 80px; bottom: 56px; padding-top: 30px; border-top: 3px solid #D6DCD7;
  display: flex; align-items: center; justify-content: space-between; gap: 32px; }
#detail { font: 700 34px/1.2 Overpass, sans-serif; color: #0D5C63; display: flex; align-items: center; gap: 16px; margin: 0; }
#detail::before { content: ""; flex: none; width: 26px; height: 26px; box-sizing: border-box; border-radius: 50%; background: #F2C34F; border: 4px solid #18241F; }
.url { font: 700 26px/1 Overpass, sans-serif; color: #55605A; margin: 0; white-space: nowrap; }
`, `
<div class="brand">${mark}<span>Badger Politics</span></div>
<div class="copy"><p id="kicker"></p><h1 id="title"></h1></div>
<div class="foot"><p id="detail"></p><p class="url">badgerpolitics.org</p></div>`);

const started = performance.now();
let next = 0;
// one browser per core: a headless background tab never paints, so tabs
// in one browser would wait on each other
const worker = async () => {
  const browser = await launchBrowser();
  try {
    const page = await cardTab(browser, html);
    while (next < cards.length) {
      const card = cards[next++];
      await page.evaluate((c) => {
        for (const k of ["kicker", "title", "detail"]) document.getElementById(k).textContent = c[k];
        document.getElementById("title").classList.toggle("long", c.title.length > 60);
      }, card);
      const out = join(DIST, card.image);
      await mkdir(dirname(out), { recursive: true });
      await shoot(page, out);
    }
  } finally {
    await browser.close();
  }
};
await Promise.all(Array.from({ length: availableParallelism() }, worker));
await rm(manifest);
console.log(`${cards.length} share cards in ${((performance.now() - started) / 1000).toFixed(1)}s`);
