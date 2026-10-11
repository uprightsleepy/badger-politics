/** Share-card plumbing for make-og.mjs and share-cards.mjs: a 1200x630
 * page set in the site's own self-hosted fonts, with the real mark. Fonts
 * are inlined as data: URLs so the page needs no file or network access. */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const local = (path) => fileURLToPath(new URL(path, import.meta.url));
const font = async (pkg, file) =>
  "data:font/woff2;base64," +
  (await readFile(local(`../../node_modules/@fontsource-variable/${pkg}/files/${file}`))).toString("base64");

export const mark = await readFile(local("../../public/mark.svg"), "utf-8");

/** A complete card document: `css` and `body` go on the brand ground. */
export const cardPage = async (css, body) => `<!doctype html><meta charset="utf-8"><style>
@font-face { font-family: Overpass; src: url(${await font("overpass", "overpass-latin-wght-normal.woff2")}); font-weight: 100 900; }
@font-face { font-family: Atkinson; src: url(${await font("atkinson-hyperlegible-next", "atkinson-hyperlegible-next-latin-wght-normal.woff2")}); font-weight: 200 800; }
html, body { margin: 0; }
body { width: 1200px; height: 630px; background: #F4F6F2; color: #18241F; font-family: Atkinson, sans-serif; position: relative; overflow: hidden; }
${css}
</style>${body}`;

/** Open a tab sized and loaded for card screenshots. */
export const cardTab = async (browser, html) => {
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  return page;
};

export const shoot = (page, path) =>
  page.screenshot({ path, clip: { x: 0, y: 0, width: 1200, height: 630 } });
