import assert from "node:assert/strict";
import { access } from "node:fs/promises";
import { test } from "node:test";
import puppeteer, { TimeoutError } from "puppeteer-core";
import { launchBrowser } from "../lib/serve.mjs";

test("the harness drives Chrome without waiting for a WebSocket endpoint", async () => {
  const browser = await launchBrowser();
  try {
    assert.equal(browser.wsEndpoint(), "");
    const page = await browser.newPage();
    await page.setContent("<main><h1>Browser ready</h1></main>");
    assert.equal(await page.$eval("h1", (el) => el.textContent), "Browser ready");
  } finally {
    await browser.close();
  }
});

for (const error of [new TimeoutError("Browser startup timed out"), new Error("Browser exited")]) {
  test(`failed startup still rejects and removes its profile: ${error.message}`, async (t) => {
    let profile;
    t.mock.method(puppeteer, "launch", async ({ userDataDir }) => {
      profile = userDataDir;
      await access(profile);
      throw error;
    });
    await assert.rejects(launchBrowser(), (actual) => actual === error);
    assert.ok(profile);
    await assert.rejects(access(profile), { code: "ENOENT" });
  });
}
