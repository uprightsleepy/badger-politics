/** Shared harness plumbing: dist path, static server, browser launch, and
 * sample-page pickers. Ports stay per-harness so parallel runs never collide. */
import { existsSync } from "node:fs";
import { createServer } from "node:http";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

export const DIST = fileURLToPath(new URL("../../dist", import.meta.url));

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/json", ".svg": "image/svg+xml",
  ".png": "image/png", ".wasm": "application/wasm", ".pf_meta": "application/octet-stream",
  ".pf_index": "application/octet-stream", ".pf_fragment": "application/octet-stream" };

export const serveDist = async (port) => {
  const server = createServer(async (req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    if (path.endsWith("/")) path += "index.html";
    try {
      const data = await readFile(join(DIST, path));
      res.writeHead(200, { "Content-Type": TYPES[extname(path)] ?? "application/octet-stream" });
      res.end(data);
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise((r) => server.listen(port, "127.0.0.1", r));
  return server;
};

// Honor BROWSER_PATH; prefer Chrome locally because Edge can exit on launch.
const LOCAL_BROWSERS = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
];

const findBrowser = () => {
  if (process.env.BROWSER_PATH) return process.env.BROWSER_PATH;
  const found = LOCAL_BROWSERS.find((p) => existsSync(p));
  if (!found) {
    throw new Error(
      "No browser found. Set BROWSER_PATH, or install one of: " +
        LOCAL_BROWSERS.join(", "),
    );
  }
  return found;
};

export const launchBrowser = async () => {
  // A fresh profile avoids handoffs to an open browser and stale profile locks.
  const userDataDir = await mkdtemp(join(tmpdir(), "bp-harness-"));
  const browser = await puppeteer.launch({
    executablePath: findBrowser(),
    headless: true,
    userDataDir,
    // the sandbox needs kernel namespaces the GitHub runner does not grant
    args: process.env.CI ? ["--no-sandbox", "--disable-dev-shm-usage"] : [],
  });
  browser.on("disconnected", () => {
    rm(userDataDir, { recursive: true, force: true }).catch(() => {});
  });
  return browser;
};

/** First href matching `pattern` on a built index page, or null. */
export const firstHref = async (indexDir, pattern) => {
  const html = await readFile(join(DIST, indexDir, "index.html"), "utf-8").catch(() => "");
  return html.match(pattern)?.[1] ?? null;
};

/** First legislator profile linked from the index, or null. */
export const firstLegislatorHref = () =>
  firstHref("legislators", /href="(\/legislators\/[^"]+\/)"/);

/** First legislator whose money card carries the quarterly chart, or null. */
export const moneyLegislatorHref = async () => {
  for (const dir of await readdir(join(DIST, "legislators")).catch(() => [])) {
    const html = await readFile(join(DIST, "legislators", dir, "index.html"), "utf-8")
      .catch(() => "");
    if (html.includes("Receipts by quarter")) return `/legislators/${dir}/`;
  }
  return null;
};

/** Shared layout/a11y coverage: page types and regression cases, augmented
 * below with dynamic links from built indexes. */
const SAMPLE_PATHS = [
  "/", "/404.html", "/about/", "/data/", "/following/", "/glossary/", "/testify/",
  "/bills/", "/bills/2025/", "/bills/2025/ab656/", "/bills/2025/ab1/", "/bills/2025/sb23/",
  "/votes/2025-av0001-ar1/", "/laws/", "/laws/2025/", "/vetoes/", "/partial-veto/",
  "/governors-desk/", "/hearing-none/", "/hearing-none/2025/", "/subjects/",
  "/legislators/", "/districts/", "/districts/senate-21/", "/committees/", "/federal/",
  "/calendar/", "/my-reps/", "/elections/2026/", "/elections/2026/senate-5/",
  "/money/", "/money/committees/", "/money/committees/651839/", "/money/independent/",
  "/local/", "/local/milwaukee/", "/local/west-allis/",
];
export const samplePages = async () => {
  const dynamic = await Promise.all([
    firstHref("subjects", /href="(\/subjects\/[^"]+\/)"/),
    firstHref("committees", /href="(\/committees\/[^"]+\/)"/),
    firstHref("federal", /href="(\/federal\/[^"]+\/)"/),
    firstHref("local/milwaukee", /href="(\/local\/milwaukee\/[^"]+\/)"/),
    // one legislator page with full cards, and one whose money card
    // carries the timeline chart (coverage differs between the two)
    firstLegislatorHref(),
    moneyLegislatorHref(),
  ]);
  return [...SAMPLE_PATHS, ...new Set(dynamic.filter(Boolean))];
};

/** Block external images, fonts, and media in layout checks to avoid source
 * latency. Keep them enabled in live CSP checks, where blocking is under test. */
export const blockThirdPartyAssets = async (page) => {
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const external = !req.url().startsWith("http://127.0.0.1");
    if (external && ["image", "font", "media"].includes(req.resourceType())) req.abort();
    else req.continue();
  });
};
