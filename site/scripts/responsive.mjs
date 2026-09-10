/** Check horizontal overflow and split campaign amounts at device widths.
 * Usage: node scripts/responsive.mjs [--shots DIR] */
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { serveDist, launchBrowser, samplePages, blockThirdPartyAssets } from "./lib/serve.mjs";

import { gotoLayoutReady } from "./lib/readiness.mjs";

const server = await serveDist(8935);
const PAGES = await samplePages();

const WIDTHS = [320, 344, 360, 412, 440, 540, 768, 1024, 1280, 1920];
const SHOT_PAGES = ["/money/", "/legislators/", "/calendar/", "/bills/2025/ab656/"];
const shotsDir = process.argv.includes("--shots")
  ? process.argv[process.argv.indexOf("--shots") + 1]
  : null;
if (shotsDir) await mkdir(shotsDir, { recursive: true });

const browser = await launchBrowser();
const page = await browser.newPage();
await blockThirdPartyAssets(page);

let failures = 0;
for (const width of WIDTHS) {
  await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
  for (const path of PAGES) {
    await gotoLayoutReady(page, `http://127.0.0.1:8935${path}`);
    const textScales = await page.$("[data-campaign-totals]") ? [1, 1.25] : [1];
    for (const textScale of textScales) {
      await page.evaluate(scale => {
        document.documentElement.style.fontSize = `${scale * 100}%`;
      }, textScale);
      const { spill, worst, brokenAmounts } = await page.evaluate(() => {
        const doc = document.documentElement;
        const spill = Math.max(doc.scrollWidth, document.body.scrollWidth) - window.innerWidth;
        // name the widest offender to make the failure actionable
        let worst = null;
        for (const el of spill > 1 ? document.querySelectorAll("body *") : []) {
          const r = el.getBoundingClientRect();
          if (r.right > window.innerWidth + 1 && (!worst || r.right > worst.right)) {
            worst = { right: r.right, tag: el.tagName, cls: (el.className?.baseVal ?? el.className ?? "").toString().slice(0, 60) };
          }
        }
        const brokenAmounts = [...document.querySelectorAll("[data-campaign-totals] dd")]
          .filter(el => {
            const range = document.createRange();
            range.selectNodeContents(el);
            const rects = [...range.getClientRects()];
            if (!rects.length) return false;
            const column = el.parentElement.getBoundingClientRect();
            const totals = el.closest("[data-campaign-totals]").getBoundingClientRect();
            return new Set(rects.map(r => r.top)).size > 1
              || rects.some(r => r.left < Math.max(column.left, totals.left) - 1
                || r.right > Math.min(column.right, totals.right) + 1);
          }).map(el => el.textContent.trim());
        return { spill, worst, brokenAmounts };
      });
      const context = `${path} @${width}px, ${textScale * 100}% text`;
      if (spill > 1) {
        failures++;
        console.log(`FAIL ${context}: ${spill}px horizontal overflow`
          + (worst ? ` (<${worst.tag.toLowerCase()} class="${worst.cls}">)` : ""));
      }
      if (brokenAmounts.length) {
        failures++;
        console.log(`FAIL ${context}: split or overflowing amounts: ${brokenAmounts.join(", ")}`);
      }
      if (shotsDir && SHOT_PAGES.includes(path)) {
        const suffix = textScale === 1 ? "" : `-${textScale * 100}pct`;
        await page.screenshot({ path: join(shotsDir, `${path.replaceAll("/", "_")}-${width}${suffix}.png`) });
      }
    }
  }
  console.log(`${width}px: ${PAGES.length} pages checked`);
}
console.log(failures ? `\n${failures} layout failures` : "\nno horizontal overflow or split campaign amounts");
await browser.close();
server.close();
process.exit(failures ? 1 : 0);
