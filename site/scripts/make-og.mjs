/** Regenerate public/og.png, the social share card. Run after a brand or
 * tagline change: `BROWSER_PATH=... node scripts/make-og.mjs`.
 *
 * Renders with the same headless browser the harness uses, so the card is
 * set in the site's own self-hosted fonts (Overpass and Atkinson
 * Hyperlegible Next) and reuses the real mark. See docs/brand.md. */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { launchBrowser } from "./lib/serve.mjs";

// fonts inline as data: URLs, so the page needs no file or network access
const font = async (pkg, file) =>
  "data:font/woff2;base64," +
  (await readFile(fileURLToPath(new URL(`../node_modules/@fontsource-variable/${pkg}/files/${file}`, import.meta.url)))).toString("base64");
const overpass = await font("overpass", "overpass-latin-wght-normal.woff2");
const atkinson = await font("atkinson-hyperlegible-next", "atkinson-hyperlegible-next-latin-wght-normal.woff2");
const mark = await readFile(fileURLToPath(new URL("../public/mark.svg", import.meta.url)), "utf-8");

const html = `<!doctype html><meta charset="utf-8"><style>
@font-face { font-family: Overpass; src: url(${overpass}); font-weight: 100 900; }
@font-face { font-family: Atkinson; src: url(${atkinson}); font-weight: 200 800; }
html, body { margin: 0; }
body { width: 1200px; height: 630px; background: #F4F6F2; color: #18241F; font-family: Atkinson, sans-serif; position: relative; overflow: hidden; }
.mark { position: absolute; left: 96px; top: 118px; width: 300px; }
.mark svg { width: 100%; height: auto; display: block; }
.copy { position: absolute; left: 470px; top: 150px; right: 80px; }
h1 { font: 800 84px/1 Overpass, sans-serif; margin: 0; letter-spacing: -0.01em; }
.tag { font: 700 34px/1.2 Overpass, sans-serif; margin: 22px 0 0; }
.sub { font-size: 29px; line-height: 1.4; color: #55605A; margin: 22px 0 0; }
.url { font: 700 28px/1 Overpass, sans-serif; color: #0D5C63; margin: 34px 0 0; }
.route { position: absolute; left: 96px; right: 96px; bottom: 64px; height: 30px; }
.road { position: absolute; top: 13px; height: 0; }
.done { left: 9px; width: 40%; border-top: 5px solid #0D5C63; }
.ahead { left: 40%; right: 9px; border-top: 5px dashed #848E88; }
.dot { position: absolute; top: 6px; width: 18px; height: 18px; border-radius: 50%; box-sizing: border-box; background: #fff; border: 4px solid #848E88; }
.dot.past { background: #0D5C63; border-color: #0D5C63; }
.dot.here { top: -1px; width: 32px; height: 32px; margin-left: -7px; background: #F2C34F; border: 4px solid #18241F; }
</style>
<div class="mark">${mark}</div>
<div class="copy">
  <h1>Badger Politics</h1>
  <p class="tag">Wisconsin's Legislature, in plain words.</p>
  <p class="sub">Every bill, where it stands, and who's behind it. Free and independent.</p>
  <p class="url">badgerpolitics.org</p>
</div>
<div class="route" aria-hidden="true">
  <div class="road done"></div><div class="road ahead"></div>
  ${[0, 20, 40, 60, 80, 100].map((x, i) => `<span class="dot ${i < 2 ? "past" : i === 2 ? "here" : ""}" style="left: calc(${x}% - ${x / 100 * 18}px)"></span>`).join("")}
</div>`;

const browser = await launchBrowser();
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  const out = fileURLToPath(new URL("../public/og.png", import.meta.url));
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: 1200, height: 630 } });
  console.log("og.png 1200x630");
} finally {
  await browser.close();
}
