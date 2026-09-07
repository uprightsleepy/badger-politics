# CI performance: first optimization pass

The three deployments examined in `research/ci-cd-performance-review.md`
took 22–24 minutes, with median stages of 9:57 for the combined build and
9:11 for verification. Dependency installation took only 5–7 seconds.
Optimize measured work without reducing gate coverage.

## Changes

- Layout and accessibility checks use `gotoLayoutReady` instead of a fixed
  network-idle wait on every page/viewport pair. It waits for deferred/module
  scripts via DOMContentLoaded, stylesheets, local images, fonts, and layout frames.
  The asynchronous calendar and following pages have explicit rendered-state
  checks. Missing required local CSS, scripts, or fonts fail the gate.
- The helper is for the anonymous sample-page walk. It is not a general
  replacement for interaction-specific readiness or saved-user-state tests.
  Add a readiness predicate when a new sample page renders asynchronous data.
- Search's no-results assertion requires the completed state for the current
  query and rejects an empty, stuck container. Fixed sleeps around initial
  search results and saved-rep pinning are replaced by observable content.
- Timings split logos, Astro, Pagefind, data products, links, each browser
  harness, and release. Each records elapsed seconds, peak RSS, and exit
  status. Logs and metrics survive failed stages and are retained for 7 days.
  Downloadable diagnostics include timings and uncredentialed build/gate logs;
  logo and release logs remain in GitHub's masked console output only.
- The deploy job now requires the reusable CI workflow for the same revision.
  Manual deployments must use main. Only the deploy job has OIDC permission.
  Ordinary push CI remains, so main can run both standalone CI and validation
  inside deploy; the short duplicate run is deliberate for an explicit gate.
- Raw database snapshots are no longer stored in Actions caches. The download
  selects the resolved GCS object generation, and records its SHA-256 in the
  run summary. New uploads use UTC timestamps and random UUIDs so multiple
  runs on one day cannot overwrite one another. Existing dated snapshots
  remain compatible. Existing `snapshot-*` Actions caches were cleared during
  implementation; until these changes reach main, an old workflow can recreate them.
- Third-party actions use full upstream commit SHAs with weekly Dependabot
  update PRs. Parsed workflow-policy checks reject mutable pins, broad write
  permissions, untrusted deployment triggers, missing CI dependencies, and
  raw-snapshot caching. Existing CI check names are preserved.
- Push filters include the data-product generator, Python dependency inputs,
  timing scripts, and CI workflow because they affect deployment behavior.

The existing sample list, seven responsive widths, two accessibility
viewports, axe rules, all-session build, exhaustive internal link checks,
preflight, manual production selection, and live smoke/CSP checks remain.
Browser harnesses still run sequentially on one runner; links run alongside.

## Validation

`cd site && npm run test:harness` requires Chrome via `BROWSER_PATH`.
On Windows, the timing-wrapper tests also require WSL with GNU `time`;
browser fixtures run in the normal Windows Node/Chrome environment.
GitHub CI uses its preinstalled Chrome; no browser download or extra npm
package is added. Local Linux environments may also need `CI=1` for the
existing sandbox launch flags.

Regression fixtures exercise delayed CSS/module loading, detectable overflow
and axe violations, missing resources, delayed/stuck calendar and following
content, and empty/stale/hidden/junk search states. Timing tests verify that
failed commands retain their nonzero exit codes and logs and that arguments
are passed literally. All tests are independent of the private snapshot and
third-party services.

### Local comparison

On the same existing local build, the original responsive harness took
214.6 seconds; the updated harness took 20.3 seconds (about 90% less time).
Both passed the identical 45-page, seven-width matrix. Accessibility fell
from 152.1 to 93.5 seconds (about 39% less time), with zero violation nodes
in both runs across the same 45 pages and two viewports. Combined, these
checks saved approximately 4m13s locally. These were single paired
Windows/Chrome runs, not GitHub runner or end-to-end deployment benchmarks.
The existing build contained the current sessions; full-history preflight
correctly rejected it before the subsequent validation rebuild.

The seven browser regression fixtures and two timing-wrapper tests passed.
Pipeline validation passed all 141 tests and Ruff; Astro checked 102 files
with zero errors. Workflow YAML and the parsed release-policy checks passed.
The subsequent full-history Astro build produced 50,405 pages. Pagefind
indexed 23,970 pages, and preflight passed all 23 sessions, 20,473 roll-call
pages, and the data-product completeness checks.
The full-build internal link scan passed 71,028 unique paths and 52,835
fragments across 50,406 HTML files. Responsive checks passed all seven
widths; accessibility reported zero violations across both viewports;
functional verification passed all 12 assertions. No release was performed,
so the workflow's post-release smoke and CSP checks await the next deployment.

## After merge

Inspect the `Deployment stage timings` job summary and diagnostics artifact
for several full dev deployments. Compare identical snapshots/build inputs
and distinguish warm from cold caches. Record sample counts and existing
harness output alongside times; a quicker incomplete check is not a success.

No before/after GitHub deployment benchmark has been run. Do not treat
local navigation savings as a measured end-to-end deployment speedup.
Use the new stage timings to choose between query profiling, bounded logo
requests, isolated verification jobs, and verified-artifact promotion.

Immutable artifact promotion and isolated browser runners remain subsequent
stages, chosen using full deployment timings and transfer/cost measurements.
