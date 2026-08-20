/** Fetch verified org logos from logo.dev into public/logos/ at build time.
 * Requires LOGO_DEV_TOKEN (free key from logo.dev); skips gracefully without
 * it (the site falls back to monogram tiles).
 * Accuracy gate: a logo is only fetched after re-verifying that the domain's
 * homepage still identifies the mapped organization. */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

// local builds keep the key in site/.env (gitignored); CI sets it in the job env
const envPath = new URL("../.env", import.meta.url);
if (!process.env.LOGO_DEV_TOKEN && existsSync(envPath)) {
  const match = (await readFile(envPath, "utf-8")).match(/^LOGO_DEV_TOKEN=(.+)$/m);
  if (match) process.env.LOGO_DEV_TOKEN = match[1].trim();
}

const token = process.env.LOGO_DEV_TOKEN;
const entries = Object.entries(
  JSON.parse(await readFile(new URL("../src/data/org-domains.json", import.meta.url), "utf-8")),
).filter(([k]) => !k.startsWith("_"));

if (!token) {
  console.log(`fetch-logos: LOGO_DEV_TOKEN not set; ${entries.length} mapped orgs will use monogram tiles`);
  process.exit(0);
}

const outDir = new URL("../public/logos/", import.meta.url);
await mkdir(outDir, { recursive: true });
let fetched = 0, failed = 0;

for (const [entityId, entry] of entries) {
  const dest = new URL(`${entityId}.png`, outDir);
  if (existsSync(dest)) continue;

  // accuracy gate: the domain must still identify the org
  const orgTokens = entry.org.toLowerCase().split(/\s+/).filter((w) => w.length > 3);
  let page = "";
  try {
    page = (await (await fetch(`https://${entry.domain}`, {
      headers: { "User-Agent": "badgerpolitics.org build (contact: hphil.work@gmail.com)" },
      redirect: "follow",
    })).text()).toLowerCase();
  } catch {}
  const identified = orgTokens.some((t) => page.includes(t));
  if (!identified) {
    console.error(`fetch-logos: GATE FAILED for ${entry.domain} (${entry.org}) — logo NOT fetched`);
    failed += 1;
    continue;
  }

  const res = await fetch(`https://img.logo.dev/${entry.domain}?token=${token}&size=64&format=png`);
  const buf = Buffer.from(await res.arrayBuffer());
  // PNG magic bytes; anything else (error JSON, placeholder HTML) is refused
  if (res.ok && buf.length > 200 && buf[0] === 0x89 && buf[1] === 0x50) {
    await writeFile(dest, buf);
    fetched += 1;
  } else {
    console.error(`fetch-logos: logo.dev returned no usable image for ${entry.domain}`);
    failed += 1;
  }
}
console.log(`fetch-logos: ${fetched} fetched, ${failed} failed/skipped, ${entries.length} mapped`);
