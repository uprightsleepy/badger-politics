/** Build-completeness gate. Runs between `npm run build` and any deploy.
 *
 * A deploy replaces the whole site, so shipping a partial build silently
 * deletes every page it omits. The default build covers two sessions;
 * production needs BUILD_SESSIONS=all. Nothing in the build itself says
 * which one you got, so this asserts the built tree against the database
 * that produced it rather than against a number someone remembered to
 * update.
 *
 * Usage: node scripts/preflight.mjs
 */
import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { DIST } from "./lib/serve.mjs";

const DB_PATH = fileURLToPath(new URL("../../data/wi.sqlite", import.meta.url));
const db = new Database(DB_PATH, { readonly: true });

let failures = 0;
const fail = (msg) => {
  console.error(`FAIL: ${msg}`);
  failures++;
};
const pass = (msg) => console.log(`ok: ${msg}`);

const exists = async (p) => {
  try {
    await stat(join(DIST, p));
    return true;
  } catch {
    return false;
  }
};

// --- every session in the database must have been built -------------------
const sessions = db
  .prepare("SELECT DISTINCT session_id FROM bills WHERE source != 'legiscan' ORDER BY session_id")
  .all()
  .map((r) => r.session_id);
// a missing directory is itself a finding, so never let it throw
const subdirs = async (...parts) => {
  try {
    return (await readdir(join(DIST, ...parts), { withFileTypes: true }))
      .filter((d) => d.isDirectory())
      .map((d) => d.name);
  } catch {
    return null;
  }
};

const builtDirs = new Set((await subdirs("bills")) ?? []);
const missing = sessions.filter((s) => !builtDirs.has(s));
if (missing.length) {
  fail(
    `${missing.length} of ${sessions.length} sessions missing from the build ` +
      `(${missing.slice(0, 5).join(", ")}${missing.length > 5 ? ", …" : ""}). ` +
      `This is a partial build — deploying it would delete those pages. ` +
      `Rebuild with BUILD_SESSIONS=all.`,
  );
} else {
  pass(`all ${sessions.length} sessions built`);
}

// --- one page per bill, per legislator, per roll call ----------------------
const counts = [
  {
    what: "bill pages",
    expected: db
      .prepare("SELECT COUNT(*) AS n FROM bills WHERE source != 'legiscan'")
      .get().n,
    dir: "bills",
    nested: true,
  },
  {
    what: "legislator pages",
    expected: db.prepare("SELECT COUNT(*) AS n FROM people").get().n,
    dir: "legislators",
    nested: false,
  },
  {
    what: "roll-call pages",
    expected: db
      .prepare(
        "SELECT COUNT(*) AS n FROM vote_events e JOIN bills b ON b.id = e.bill_id" +
          " WHERE b.source != 'legiscan'",
      )
      .get().n,
    dir: "votes",
    nested: false,
  },
];

for (const c of counts) {
  let built = 0;
  if (c.nested) {
    for (const session of builtDirs) {
      built += ((await subdirs(c.dir, session)) ?? []).length;
    }
  } else {
    built = ((await subdirs(c.dir)) ?? []).length;
  }
  if (built < c.expected) {
    fail(`${c.what}: built ${built}, database has ${c.expected}`);
  } else {
    pass(`${c.what}: ${built} built for ${c.expected} rows`);
  }
}

// --- council member pages mirror the local tables, when present ------------
const hasLocal = db
  .prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_members'")
  .get();
if (hasLocal) {
  const expected = db
    .prepare(
      "SELECT COUNT(*) AS n FROM local_members m WHERE m.is_current = 1" +
        " OR EXISTS (SELECT 1 FROM local_votes v WHERE v.tenant = m.tenant" +
        " AND v.person_id = m.person_id)",
    )
    .get().n;
  let built = 0;
  for (const bodyDir of (await subdirs("local")) ?? []) {
    built += ((await subdirs("local", bodyDir)) ?? []).length;
  }
  if (built < expected) {
    fail(`council member pages: built ${built}, database has ${expected}`);
  } else {
    pass(`council member pages: ${built} built for ${expected} members`);
  }
}

// --- the search index has to match the build it shipped with ---------------
const pfPath = join(DIST, "pagefind", "pagefind-entry.json");
if (!(await exists("pagefind/pagefind-entry.json"))) {
  fail("no pagefind index — the site would ship with search broken");
} else {
  const entry = JSON.parse(await readFile(pfPath, "utf-8"));
  const indexed = Object.values(entry.languages ?? {}).reduce(
    (sum, l) => sum + (l.page_count ?? 0),
    0,
  );
  // roll-call pages are deliberately excluded from the index
  const floor = counts[0].expected;
  if (indexed < floor) {
    fail(`search index has ${indexed} pages, fewer than the ${floor} bills alone`);
  } else {
    pass(`search index: ${indexed} pages`);
  }
}

// --- data products come from the Python pipeline, not the site build ------
// They are gitignored, so a site-only build produces a tree that looks
// complete and silently drops every feed, API file and calendar.
const products = [
  { what: "legislator feeds", dir: ["feeds", "legislators"], min: counts[1].expected },
  { what: "bill feeds", dir: ["feeds", "bills"], min: 1 },
  { what: "JSON API", dir: ["api", "v1"], min: 1 },
  { what: "calendars", dir: ["calendar"], min: 1 },
];
for (const p of products) {
  let n = 0;
  try {
    n = (await readdir(join(DIST, ...p.dir))).length;
  } catch {
    n = 0;
  }
  if (n < p.min) {
    fail(
      `${p.what}: ${n} files in ${p.dir.join("/")}, expected at least ${p.min}. ` +
        `Run \`python -m dataproducts.build\` before building the site.`,
    );
  } else {
    pass(`${p.what}: ${n} files`);
  }
}

// --- discoverability ------------------------------------------------------
// A missing sitemap or robots.txt breaks nothing a visitor can see, which
// is exactly why it would go unnoticed on a 44,000-page site.
for (const f of ["robots.txt", "sitemap-index.xml"]) {
  if (!(await exists(f))) fail(`missing ${f}`);
  else pass(`${f} present`);
}
const robots = await readFile(join(DIST, "robots.txt"), "utf-8").catch(() => "");
if (!robots.includes("sitemap-index.xml")) {
  fail("robots.txt does not point at the sitemap");
}

// --- pages that must never 404 --------------------------------------------
let missingPages = 0;
for (const p of [
  "index.html",
  "404.html",
  "my-reps/index.html",
  "bills/index.html",
  "legislators/index.html",
  "money/index.html",
  "about/index.html",
]) {
  if (!(await exists(p))) {
    fail(`missing ${p}`);
    missingPages++;
  }
}
if (!missingPages) pass("landing pages present");

// --- the disclaimer is a hard rule, so assert it shipped -------------------
const home = await readFile(join(DIST, "index.html"), "utf-8").catch(() => "");
if (!/not affiliated with the State of Wisconsin/i.test(home)) {
  fail("homepage is missing the independence disclaimer");
} else {
  pass("independence disclaimer present");
}

console.log(
  failures === 0
    ? "\npreflight passed — safe to deploy"
    : `\npreflight FAILED with ${failures} problem(s) — refusing to deploy`,
);
process.exit(failures === 0 ? 0 : 1);
