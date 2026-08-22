/** Shared harness plumbing: dist path, static server, browser launch, and
 * sample-page pickers. Ports stay per-harness so parallel runs never collide. */
import { createServer } from "node:http";
import { readFile, readdir } from "node:fs/promises";
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

export const launchBrowser = () =>
  puppeteer.launch({
    executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    headless: true,
  });

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
