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

// CI exports BROWSER_PATH. Locally, try Chrome before Edge: Edge 151
// exits 0 the instant puppeteer launches it, which surfaces only as
// "Failed to launch the browser process: Code: 0". Chrome at the same
// version drives fine.
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
  // A fresh profile per run. Sharing one with the developer's own browser
  // makes the launch hand off to it and exit 0; sharing a fixed temp path
  // between runs leaves a lock behind whenever a run is killed. Either way
  // the harness fails for reasons unrelated to the site.
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

/** First legislator profile linked from the index, or null. */
export const firstLegislatorHref = async () => {
  const idx = await readFile(join(DIST, "legislators/index.html"), "utf-8").catch(() => "");
  return idx.match(/href="(\/legislators\/[^"]+\/)"/)?.[1] ?? null;
};

/** First legislator whose money card carries the quarterly chart, or null. */
export const moneyLegislatorHref = async () => {
  for (const dir of await readdir(join(DIST, "legislators")).catch(() => [])) {
    const html = await readFile(join(DIST, "legislators", dir, "index.html"), "utf-8")
      .catch(() => "");
    if (html.includes("Receipts by quarter")) return `/legislators/${dir}/`;
  }
  return null;
};
