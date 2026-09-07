/** Layout/a11y readiness for the anonymous sample-page walk. DOMContentLoaded
 * includes deferred/module scripts; CSS, fonts and async page content have
 * their own gates. No fixed network-idle delay on every page/viewport pair.
 * Functional interactions and the live CSP probe keep their own waits. */
export const gotoLayoutReady = async (page, url, { timeout = 60000 } = {}) => {
  const deadline = Date.now() + timeout;
  const remaining = () => Math.max(1, deadline - Date.now());
  const failures = new Set();
  const isRequired = (request) => new URL(request.url()).origin === new URL(url).origin
    && ["stylesheet", "script", "font"].includes(request.resourceType());
  const onResponse = (response) => {
    if (isRequired(response.request()) && response.status() >= 400) {
      failures.add(`${response.status()} ${response.url()}`);
    }
  };
  const onFailure = (request) => {
    if (isRequired(request)) failures.add(`${request.failure()?.errorText} ${request.url()}`);
  };
  page.on("response", onResponse);
  page.on("requestfailed", onFailure);
  try {
    const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: remaining() });
    if (!response?.ok()) throw new Error(`Layout navigation failed: ${url} (${response?.status()})`);

    await page.waitForFunction(() =>
      [...document.querySelectorAll('link[rel="stylesheet"]')].every((link) => link.sheet),
    { timeout: remaining() });

    const path = new URL(url).pathname;
    if (path === "/calendar/") {
      await page.waitForFunction(() => {
        const label = document.getElementById("month-label")?.textContent?.trim();
        return label && label !== "Loading calendar…" && label !== "Calendar unavailable"
          && document.querySelector("#grid")?.children.length >= 28
          && document.getElementById("day-panel")?.classList.contains("hidden") === false;
      }, { timeout: remaining() });
    }
    if (path === "/following/") {
      await page.waitForFunction(() =>
        /followed items? loaded/.test(document.getElementById("follow-status")?.textContent ?? ""),
      { timeout: remaining() });
    }

    // Local images can set intrinsic dimensions after DOMContentLoaded.
    // Include images visible at this viewport (even lazy-loaded ones), plus
    // eager images; leave offscreen lazy images lazy, as in the old harness.
    await page.waitForFunction(() => [...document.images].every((img) => {
      const src = img.currentSrc || img.src;
      if (!src || new URL(src, location.href).origin !== location.origin) return true;
      const rect = img.getBoundingClientRect();
      // A visible image may be zero-sized until its intrinsic size arrives.
      const visible = img.getClientRects().length > 0
        && rect.bottom >= 0 && rect.top < innerHeight
        && rect.right >= 0 && rect.left < innerWidth;
      if (img.loading === "lazy" && !visible) return true;
      return img.complete;
    }), { timeout: remaining() });
    const brokenImages = await page.evaluate(() => [...document.images]
      .filter((img) => img.currentSrc && new URL(img.currentSrc).origin === location.origin
        && img.complete && img.naturalWidth === 0)
      .map((img) => img.currentSrc));
    if (brokenImages.length) throw new Error(`Required layout images failed: ${brokenImages.join(", ")}`);

    // Fonts can start loading when async content is inserted. Wait after the
    // content gates, then let style/layout settle before measuring or running axe.
    await page.waitForFunction(async () => {
      await document.fonts.ready;
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return true;
    }, { timeout: remaining() });
    if (failures.size) throw new Error(`Required layout resources failed: ${[...failures].join(", ")}`);
  } finally {
    page.off("response", onResponse);
    page.off("requestfailed", onFailure);
  }
};

/** An empty container is not proof that a search completed successfully. */
export const waitForNoSearchResults = async (page, query, { timeout = 30000 } = {}) => {
  await page.waitForFunction((expectedQuery) => {
    const box = document.getElementById("search-results");
    return document.getElementById("q")?.value === expectedQuery
      && document.getElementById("search-status")?.textContent === "No results."
      && box && !box.classList.contains("hidden")
      && box.textContent.includes(`Nothing matches “${expectedQuery}”`)
      && box.querySelectorAll(":scope > a").length === 0;
  }, { timeout }, query);
};
