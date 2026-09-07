# CI/CD Performance and Quality Review

Reviewed September 6, 2026, at commit `f5f97ed3002d9471991589d0f06df74aef0d6cb8`.

Implementation update: the initial optimization pass is now applied in the
working tree; see [changes and validation](../ci-performance.md). The findings
and baseline below describe the repository before that implementation.

This is a draft improvement plan based on repository code and actual GitHub Actions timings. No workflows, application code, cloud settings, or deployments were changed. The existing untracked `badger-politics-ci-improvements.patch` was inspected but not applied or executed.

## What actually takes 20 minutes

The ordinary CI workflow is already fast: recent successful runs finished in **26–36 seconds**, including runner startup. Deployment is the bottleneck.

| Successful deployment | Total elapsed | Build every session | Verify built site | Release | Data products |
| --- | ---: | ---: | ---: | ---: | ---: |
| [September 3, dev](https://github.com/uprightsleepy/badger-politics/actions/runs/33715717715) | 23m58s | 8m58s | 8m40s | 4m08s | 37s |
| [September 3, prod](https://github.com/uprightsleepy/badger-politics/actions/runs/33717260093) | 23m31s | 10m16s | 9m11s | 2m11s | 34s |
| [September 2, prod](https://github.com/uprightsleepy/badger-politics/actions/runs/33668723728) | 22m22s | 9m57s | 9m16s | 1m07s | 33s |

Totals use workflow creation/completion timestamps; stage durations use job step timestamps. Remaining time includes setup, snapshot handling, live checks, cleanup, and scheduling. These three runs establish a baseline, not a statistical performance guarantee.

The latest production log provides more detail:

- Astro built **50,405 pages in 9m04s**. Vite compilation took only about eight seconds; static route generation occupied most of the build.
- Pagefind took **69.7 seconds**, indexing 23,970 pages.
- Responsive verification took approximately **4m51s**; accessibility took **4m14s**; functional verification took about **7 seconds**, inferred from sequential harness completion timestamps.
- The accessibility sample contained **45 pages**. Responsive coverage uses seven widths; accessibility uses two viewports.
- Firebase found **137,747 files**, uploading 51,111 new files. Its release step includes CLI startup/install, file processing, upload, and publication.
- Logos were skipped because `LOGO_DEV_TOKEN` was unset. Logo fetching did not cause this run's delay.
- npm installation and the named native rebuild took **5–7 seconds**. A snapshot cache miss downloaded in about **two seconds**.

Build and verification account for roughly 83% of the latest production run. Dependency tuning and reducing the short CI checks should not lead this work.

## Recommended improvements, in order

### 1. Replace repeated network-idle waits with tested readiness conditions

**Evidence:** `site/scripts/responsive.mjs:28` and `site/scripts/a11y.mjs:27` navigate every page/viewport pair using `networkidle2`. Across the measured sample, that is 315 responsive navigations plus 90 accessibility navigations.

Puppeteer's `networkidle2` requires at most two network connections for at least 500 ms. The 405 navigations therefore contain approximately **202.5 seconds of idle-window requirements**. This is an optimization opportunity, not guaranteed savings: loading and application readiness can overlap that interval. [Puppeteer lifecycle documentation](https://pptr.dev/api/puppeteer.puppeteerlifecycleevent).

**Draft change:** Introduce a shared navigation helper that waits for successful document loading, required styles/scripts, fonts, relevant local image completion, and completion of asynchronous page content such as the calendar and following view. Use explicit UI conditions for functional assertions. Keep every sampled page, width, axe rule, and zero-violation requirement.

**Acceptance:** Run old and new harnesses against the same full build. Add fixtures proving that delayed CSS, fonts, local images, calendar data, and module initialization cannot produce premature passes. Deliberately broken layout, accessible names, missing pages, and required resources must still fail. Record navigation versus axe execution time separately.

**Expected impact:** Several minutes are plausible; benchmark before claiming a reduction. This is the best initial performance change with limited architectural scope.

### 2. Promote the exact verified dev version to production

**Evidence:** The September 3 dev and prod runs use the same commit, but `deploy.yml` resolves the newest snapshot and rebuilds/rechecks everything independently. Production promotion took another 23m31s. A new snapshot or changed environment input can also make production differ from the dev output the owner reviewed.

**Draft change:** Build and run all gates once on dev. Record a release manifest containing the commit, immutable snapshot identity, build configuration, tool versions, successful gate results, and Firebase version ID. Manual production promotion selects that exact approved version.

Firebase supports cloning a specific version, including across Hosting sites/projects. Prefer the recorded version ID over the moving `dev:live` channel. Alternatively, deploy an immutable, verified archive of the same output. [Firebase version cloning](https://firebase.google.com/docs/hosting/manage-hosting-resources).

**Acceptance:** Production cannot promote a failed, unverified, expired, or mismatched version. Verify compatibility of target-specific configuration, especially `PUBLIC_PLACES_KEY` restrictions, headers, and redirects. Preserve manual production selection, environment protections, target serialization, live smoke/CSP checks, and a recorded rollback version. Define a maximum acceptable age for date-dependent pages. Rebuild and reverify whenever inputs must change.

**Expected impact:** Avoids repeating the measured **19m27s of build plus verification** on this production run, plus some preparation/upload work. A promotion lasting a few minutes is a reasonable target, not a measured result. This improves production promotion, not the first dev build.

### 3. Run browser gates on separate runners if transfer costs justify it

**Evidence:** `deploy.yml` intentionally runs responsive, accessibility, and functional checks sequentially: concurrent Chrome instances previously caused resource starvation on one runner. Links already run alongside them.

**Draft change:** Build once, run preflight, then package the complete output as one archive. Independent verification jobs consume the same identified artifact; the release job requires all of them. Keep browser jobs uncredentialed and scope deployment credentials to release. Measure archive size, transfer time, memory, and runner minutes before choosing this layout.

**Expected impact:** With current timings, responsive and accessibility on independent runners could reduce the approximately 9m11s verification stage toward the longest branch, approximately 4m51s, **before transfer/setup overhead**. Faster readiness will change this calculation. Do not add these savings mechanically to recommendation 1.

**Acceptance:** Failures in any branch prevent release. Retain complete diagnostics even when another branch fails. Compare cost and elapsed time; do not run three Chrome instances concurrently on the existing runner or purchase larger runners without evidence.

### 4. Profile static rendering, then remove repeated database work

**Evidence:** `site/src/lib/db.ts` already caches prepared statements and several computed results, but `billsFor`, `votesFor`, and `voteRecordsFor` still execute and allocate on every call. The paginated bill routes repeatedly load a whole session and slice/filter it. `votes/[id].astro` queries votes per bill during route discovery and again for sibling links; `RollCall.astro` loads records on bill and standalone vote pages.

**Draft change:** Add opt-in aggregate query counters/timers and route-family timings. Investigate reusable session lists, one grouped vote-event query for route discovery, and bounded reuse of repeated results. Use `EXPLAIN QUERY PLAN` on the measured expensive queries; the schema already has indexes for the obvious bill/event/person lookups.

**Acceptance:** Same complete route set, provenance filtering, ordering, tally values, search coverage, and passing gates. Measure peak memory as well as time: caching all historical vote rows may cost more than it saves. Avoid mutating arrays shared by cached callers. Optimize rendering/components if profiling shows SQL is a small fraction.

**Expected impact:** Unknown until profiled. The nine-minute Astro phase is large enough to justify investigation; code inspection alone does not establish the dominant function.

### 5. Add stage timings and retain diagnostic output

Split logo fetching, Astro, and Pagefind into separately timed steps; time each browser harness and links independently. Record elapsed time, peak memory, exit status, sample counts, and output counts in a run summary. Keep short-lived, sanitized diagnostic artifacts on failures too.

The current verification wrapper only prints the last few log lines. Its final `links passed` timestamp occurs when the workflow waits for that process, so it cannot establish how long links actually ran. The release step likewise needs separate CLI setup and deploy timings.

This instrumentation is a prerequisite for evaluating the changes above and preventing gradual regressions.

## Quality and security issues to address alongside performance

### High priority: private snapshot is cached outside its private access boundary

`deploy.yml:89–94` stores `data/wi.sqlite.gz` in an Actions cache. GitHub documents that pull requests, including forks, can access base-branch caches. A private GCS bucket does not make that cached copy private. This is an exposure path; this review did not inspect cache contents or establish whether anyone retrieved them. [GitHub cache access documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

Remove raw snapshots from Actions caching and remove existing matching cache entries as a separate operational change. Continue authenticated downloads from the private bucket. If caching is needed later, use access-controlled storage or deliberately public, provenance-filtered products. In the measured runs, uncached downloads took about two seconds, so this security fix has little runtime cost; monitor additional egress against the budget.

### High priority: same-day snapshot replacement can reuse stale data

`pipeline/run.sh:100` uploads to a date-only name, while `deploy.yml:94` keys the cache by that filename. A second upload on the same date can change the object while the immutable Actions cache still supplies the first copy. Integrity checks can pass on a valid but outdated database.

Publish unique snapshot names and record a generation/content checksum and producer revision. Download the resolved generation and verify its identity. Link producer integrity-gate results to that snapshot; `PRAGMA quick_check` and a bill-count floor do not establish domain correctness or freshness. Removing the Actions cache fixes the immediate cache collision, but immutable identity is still necessary for reproducible promotion.

### High priority: deploy does not depend on successful CI for its revision

`ci.yml` and `deploy.yml` are independent workflows. The deploy job has no dependency on the CI result, including on manual dispatch. A failed Ruff, pytest, typecheck, or infrastructure check does not structurally block publication in this workflow. Branch/environment protections were not audited here and may provide additional controls.

Use a reusable validation workflow or a combined dependency graph that gates publication on successful checks for the exact revision. CI can overlap the expensive build; release must wait for both. Preserve existing required-check names. If reusing the draft patch's `needs: validate` approach, note that it serializes validation ahead of the build and duplicates standalone push CI; the measured cost is small, but intentional orchestration is cleaner.

### Medium priority: workflow security checks overstate what they validate

The job named `workflows pinned + least privilege` uses grep to check permissions and PR deploy triggers. It does not enforce immutable action pins; actions use mutable major tags. The Firebase CLI is fetched at release time with `npx --yes firebase-tools@14`, outside a committed lockfile.

Pin third-party actions to reviewed full commit SHAs, automate update PRs, and lock deployment tooling separately from runtime site dependencies. Keep `npm ci --ignore-scripts` and the named `better-sqlite3` rebuild. Validate parsed workflow structure and explicit job permissions rather than relying only on text matching. [GitHub secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use).

### Medium priority: release triggers and the alternate release path can drift

The deploy push filter excludes `pipeline/dataproducts/**` and its dependency inputs even though they affect published output. Include those inputs and validation workflow changes in the trigger model. Importer/schema changes additionally need a compatible regenerated snapshot; merely triggering a site build does not produce one.

`pipeline/run.sh:91` can publish after importer checks and preflight without the workflow's browser/link gates. Align this supported script and the older `CLAUDE.md`/deployment instructions with the intended Actions-only release policy. Prefer making the pipeline produce verified snapshots and routing publication through the common release gates.

### Medium priority: scraper policy compliance should be operational, not only documented

The shared `pipeline/scraper/http.py` identifies the crawler, retries, and caches pages, but does not centrally enforce robots rules or host pacing. Some fetchers document manual source reviews. `site/scripts/fetch-logos.mjs` also gathers third-party pages, with sequential requests and no explicit fetch timeout.

Maintain source-specific policy records with URLs, review dates, permitted paths, and rate limits. Add policy-aware host throttling and bounded requests where appropriate, including logo verification. Follow the new `AGENTS.md` rules when changing gatherers. Preserve organization verification when caching logos. This improves reliability/compliance, but logos were disabled and scrapers do not run in the measured deploys, so it will not explain their current runtime.

## Assessment of the existing improvement patch

The untracked patch already proposes useful work: stage timings, readiness helpers and regression fixtures, stronger no-results assertions, expanded deployment triggers, and explicit CI gating. It is a sensible starting point for recommendations 1 and 5.

It has not been applied, executed, or benchmarked in this review. Its layout helper checks styles, fonts, and selected async content, but does not explicitly await local images; include delayed-image coverage before replacing the old navigation waits. It also leaves snapshot caching, immutable promotion, and action pinning for follow-up. Treat its performance claims as unmeasured.

## Suggested delivery sequence and success criteria

1. Address raw-snapshot caching and snapshot identity; add timing/log retention and explicit CI release gating.
2. Implement and compare readiness behavior on the same full build; preserve all current gates and sample dimensions.
3. Establish immutable dev-to-prod promotion with identity, freshness, configuration, and rollback checks.
4. Use the new timings to choose isolated verification jobs and targeted render/query improvements.

For each performance change, compare several runs with the same commit, snapshot, and configuration; distinguish cold/warm installs and report median, slowest run, failure/retry rate, and runner cost. Confirm full-history pages, feeds/API/calendars, search, provenance, and live CSP checks still pass.

Do not reduce test coverage, drop history, reuse stale `dist/`, weaken integrity gates, or increase source request rates to meet a time target. Historical page caching is a later project: shared layouts, CSS, scripts, curation corrections, date-dependent UI, and search all complicate invalidation.

This review used read-only code inspection and three successful deployment runs, plus recent CI metadata. No full local build or performance experiment was run. Reported baseline times are measured; projected improvements require implementation and validation.
