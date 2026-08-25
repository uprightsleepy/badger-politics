/** Regenerate public/og.png, the social share card. Run after a brand or
 * tagline change: `node scripts/make-og.mjs`. Reuses the real favicon
 * artwork so the card can never drift from the site's mark. */
import { readFile, writeFile } from "node:fs/promises";
import sharp from "sharp";

const fav = await readFile("public/favicon.svg", "utf-8");
const inner = fav.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#16233a"/>
  <rect x="0" y="610" width="1200" height="20" fill="#c9962e"/>
  <svg x="88" y="150" width="320" height="320" viewBox="0 0 1000 1000">${inner}</svg>
  <text x="468" y="248" font-family="Georgia, 'Times New Roman', serif" font-size="80" font-weight="700" fill="#ffffff">Badger Politics</text>
  <text x="468" y="314" font-family="Georgia, 'Times New Roman', serif" font-size="34" fill="#c9962e">Wisconsin&#8217;s Legislature, in plain sight.</text>
  <text x="468" y="388" font-family="Arial, Helvetica, sans-serif" font-size="27" fill="#d9e2ee">Every bill. Every vote. Every committee graveyard.</text>
  <text x="468" y="434" font-family="Arial, Helvetica, sans-serif" font-size="27" fill="#d9e2ee">Free, independent, and never behind a login.</text>
  <text x="468" y="512" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700" fill="#c9962e">badgerpolitics.org</text>
</svg>`;

await writeFile("scripts/.og.svg", svg);
await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile("public/og.png");
const m = await sharp("public/og.png").metadata();
console.log(`og.png ${m.width}x${m.height}`);
