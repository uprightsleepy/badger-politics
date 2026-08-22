/** Responsive smoke test: every scanned page at seven device widths,
 * asserting the page never scrolls horizontally (the classic mobile
 * degradation). Usage: node scripts/responsive.mjs [--shots DIR] */
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { serveDist, launchBrowser, moneyLegislatorHref } from "./lib/serve.mjs";

const server = await serveDist(8935);

const PAGES = [
  "/", "/bills/", "/bills/2025/", "/bills/2025/ab656/", "/votes/2025-av0001-ar1/",
  "/legislators/", "/hearing-none/2025/", "/calendar/", "/my-reps/",
  "/elections/2026/", "/data/", "/about/", "/money/", "/money/committees/",
  "/money/committees/651839/", "/404.html",
];
const moneyHref = await moneyLegislatorHref();
if (moneyHref) PAGES.push(moneyHref);

// fold cover screen, small phone, phone, foldable half, tablet portrait,
// laptop, widescreen
const WIDTHS = [344, 360, 412, 540, 768, 1280, 1920];
const SHOT_PAGES = ["/money/", "/legislators/", "/calendar/", "/bills/2025/ab656/"];
const shotsDir = process.argv.includes("--shots")
  ? process.argv[process.argv.indexOf("--shots") + 1]
  : null;
if (shotsDir) await mkdir(shotsDir, { recursive: true });

const browser = await launchBrowser();
const page = await browser.newPage();
let failures = 0;
for (const width of WIDTHS) {
  await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
  for (const path of PAGES) {
    await page.goto(`http://127.0.0.1:8935${path}`, { waitUntil: "networkidle2", timeout: 30000 });
    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      const spill = Math.max(doc.scrollWidth, document.body.scrollWidth) - window.innerWidth;
      if (spill <= 1) return null;
      // name the widest offender to make the failure actionable
      let worst = null;
      for (const el of document.querySelectorAll("body *")) {
        const r = el.getBoundingClientRect();
        if (r.right > window.innerWidth + 1 && (!worst || r.right > worst.right)) {
          worst = { right: r.right, tag: el.tagName, cls: (el.className?.baseVal ?? el.className ?? "").toString().slice(0, 60) };
        }
      }
      return { spill, worst };
    });
    if (overflow) {
      failures++;
      console.log(`FAIL ${path} @${width}px: ${overflow.spill}px horizontal overflow`
        + (overflow.worst ? ` (<${overflow.worst.tag.toLowerCase()} class="${overflow.worst.cls}">)` : ""));
    }
    if (shotsDir && SHOT_PAGES.includes(path)) {
      await page.screenshot({ path: join(shotsDir, `${path.replaceAll("/", "_")}-${width}.png`) });
    }
  }
  console.log(`${width}px: ${PAGES.length} pages checked`);
}
console.log(failures ? `\n${failures} overflow failures` : "\nno horizontal overflow at any width");
await browser.close();
server.close();
process.exit(failures ? 1 : 0);
