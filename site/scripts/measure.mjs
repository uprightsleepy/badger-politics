/** Name what overflows a narrow viewport on one built page.
 *
 * The responsive gate says a page spills; this says which element, and
 * it can force a wide font so a Windows pass can reproduce a Linux CI
 * failure (system fonts differ by roughly the margins CI reports).
 * Usage: node scripts/measure.mjs /local/west-allis/ [width] [--wide-font]
 */
import { serveDist, launchBrowser, blockThirdPartyAssets } from "./lib/serve.mjs";

const [path, widthArg] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const width = Number(widthArg ?? 344);
const wideFont = process.argv.includes("--wide-font");
const server = await serveDist(8937);
const browser = await launchBrowser();
const page = await browser.newPage();
await blockThirdPartyAssets(page);
await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
if (wideFont) {
  await page.evaluateOnNewDocument(() => {
    document.addEventListener("DOMContentLoaded", () => {
      const s = document.createElement("style");
      s.textContent = "* { font-family: Verdana, sans-serif !important; }";
      document.head.appendChild(s);
    });
  });
}
await page.goto(`http://127.0.0.1:8937${path}`, { waitUntil: "networkidle2", timeout: 60000 });
const report = await page.evaluate(() => {
  const doc = document.documentElement;
  const spill = Math.max(doc.scrollWidth, document.body.scrollWidth) - window.innerWidth;
  const wide = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    const over = Math.max(r.right - window.innerWidth, el.scrollWidth - el.clientWidth);
    if (over > 1 && r.width > 0) {
      wide.push({
        over: Math.round(over), right: Math.round(r.right), w: Math.round(r.width),
        tag: el.tagName.toLowerCase(),
        cls: (el.className?.baseVal ?? el.className ?? "").toString().slice(0, 70),
        text: (el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 60),
      });
    }
  }
  wide.sort((a, b) => b.over - a.over);
  return { spill, wide: wide.slice(0, 8) };
});
console.log(`${path} @${width}px${wideFont ? " (Verdana forced)" : ""}: spill ${report.spill}px`);
for (const w of report.wide) console.log(`  +${w.over}px right=${w.right} w=${w.w} <${w.tag} class="${w.cls}"> "${w.text}"`);
await browser.close();
server.close();
