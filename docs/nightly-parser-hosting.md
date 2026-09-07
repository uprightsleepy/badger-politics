# Nightly parser hosting and operations

Implementation dated 2026-09-07. The workflow and resumable parser are
implemented, and the GCP IAM/storage plan has been applied. Scheduled
collection is disabled unless the repository variable
`NIGHTLY_PARSER_ENABLED` is explicitly set to `true`. Seed and rehearse before
enabling it. Infrastructure application is recorded separately below.

## Recommendation and cost goals

Run the parser on a **standard Linux GitHub-hosted runner** in this public
repository. Reuse the private `badgerpolitics-prod-snapshots` bucket for
compressed source state and validated SQLite snapshots. Keep site releases
in the existing gated `deploy.yml` workflow, with production promotion
remaining explicit.

`AGENTS.md` sets a total infrastructure ceiling below $10/month excluding
domains and prefers $0–5. `CLAUDE.md` and the README retain the older
approximately $2/month target; `CLAUDE.md` also rejects additional paid
GCP resources. Design for $2, including existing hosting, storage, data
ingestion, and API usage. This draft adds no compute, scheduler, registry,
database, or new bucket. IAM has no standing compute charge; storing and
moving additional data in the existing bucket still needs a usage budget.

Standard GitHub-hosted runner compute is free for public repositories.
This avoids a compute bill growing with a slow, politely throttled scrape.
The recommendation depends on the repository remaining public and using
standard runners. [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

## What the current pipeline needs

`pipeline/run.sh` does much more than parse a new download: it scrapes,
rebuilds SQLite from current and archived sessions, imports offline data,
enriches records, checks integrity, builds the whole static site, deploys,
and uploads a snapshot. `--skip-deploy` still builds the site. The nightly
workflow instead runs the parser-only stages in `pipeline/nightly/`.
`pipeline/Dockerfile` is an unused placeholder; runners install the pinned
scraper CLI separately from the pipeline environment using upstream's
existing Poetry lock, exported with hashes and platform markers.

A fresh runner cannot start with just a SQLite snapshot. Preserve the raw
archive, historical sessions, WEC reports, lobbying and WisconsinEye
offline inputs, and the HTTP/enrichment caches under `pipeline/_data/`.
Without them an import can lose history, fail on missing files, or repeat
large downloads. Keep paused sources paused and retain the current source
access checks; this draft does not initiate or alter collection.

At review time the bucket is regional Standard storage in `us-central1`,
with uniform bucket access, public access prevention, a blanket 30-day
delete rule, and seven-day soft delete. Its live objects total about
2.06 GiB; this does not include soft-deleted bytes. The local source archive
is about 3.56 GiB uncompressed, plus about 0.85 GiB in the upstream scraper's
`_cache/`. Both are included in the source seed. Cloud Run and Cloud Scheduler APIs are
disabled in the production project. No end-to-end nightly runtime or peak
memory benchmark has been established.

## Cost comparison

Cloud Run remains a fallback if the scraper cannot be split into jobs that
fit the hosted runner limit or needs stronger scheduling guarantees. First
prefer checkpointed, sequential Actions jobs for a multi-hour pipeline.
Cloud Run's free allowance
is shared across a billing account: 240,000 vCPU-seconds and 450,000
GiB-seconds monthly. Jobs are billed for their full instance lifetime,
including time waiting for upstream sites. In Iowa, excess usage is
$0.000018/vCPU-second and $0.000002/GiB-second.
[Cloud Run pricing](https://cloud.google.com/run/pricing)

Illustrative 30-night compute costs, **not measured runtimes**:

| Host / allocation | Minutes per night | Monthly compute after unused free allowance |
| --- | ---: | ---: |
| Public GitHub Actions, standard Linux | 30–330 per job | $0 |
| Cloud Run, 2 vCPU / 8 GiB | 30 | $0 |
| Cloud Run, 2 vCPU / 8 GiB | 60 | $0.83 |
| Cloud Run, 2 vCPU / 8 GiB | 120 | $6.01 |
| Cloud Run, 2 vCPU / 8 GiB | 180 | $11.63 |
| Cloud Run, 2 vCPU / 8 GiB | 240 | $17.24 |
| Cloud Run, 2 vCPU / 8 GiB | 360 | $28.48 |
| Cloud Run, 2 vCPU / 8 GiB | 480 | $39.71 |

Four to eight hours every night is 120–240 runner-hours in a 30-day month.
Public standard-runner compute remains $0 for that use; paid private-repo
minute allowances are not the limit here. However, **each hosted job has
a six-hour maximum**, including setup and state transfer. Plan for a
330-minute job timeout with collection stages bounded below five hours,
leaving time for state restoration, checks, and upload. Treat long nightly
execution as the baseline to measure, not a reason to assume free Cloud Run.
[Actions execution limits](https://docs.github.com/en/actions/reference/limits)

An eight-hour pipeline can use sequential jobs in one workflow, each
restoring only its required inputs and handing immutable checkpoints to
the next job. Do not split it into independently scheduled, overlapping
scrapers or reduce source delays to meet a time limit. Use source or date
boundaries that preserve the cumulative import. If the Wisconsin scraper
alone exceeds the limit, it needs a supported resumable boundary before
Actions can host it reliably; a longer overall workflow timeout cannot
extend an individual job's six-hour limit. Keep publication after all
stages and final integrity checks.

The Cloud Run examples exclude storage, network, scheduler, image storage,
and other projects consuming the free allowance. Its writable filesystem
uses instance memory, so restoring several GiB of source files must be
included in sizing; an apparently cheap 1–2 GiB configuration is not a
safe assumption. [Cloud Run filesystem contract](https://cloud.google.com/run/docs/container-contract#file_system)

Cloud Scheduler includes three jobs per billing account, then costs
$0.10/job/month. Artifact Registry includes 0.5 GB of storage and charges
for additional image storage; a working pipeline image has not been sized.
An always-on VM would also require sizing, patching, and network cost
review. Neither adds a cost advantage over free Actions compute here.
[Scheduler pricing](https://cloud.google.com/scheduler/pricing),
[Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)

## Storage and transfer budget

Cloud Storage's eligible US regional free allowance includes 5 GB-months,
5,000 Class A operations, 50,000 Class B operations, and 100 GB monthly
outbound transfer from North America excluding China and Australia.
Free allowances are shared; available headroom has not been verified
against the whole billing account. Use compressed bundles rather than
uploading tens of thousands of individual files each night.
[Google Cloud free tier](https://docs.cloud.google.com/free/docs/free-cloud-features)

Model one complete compressed state bundle of `R` GiB per successful night,
one persistent seed of the same size, and one `S` GiB SQLite snapshot.
Seven live checkpoint days plus seven soft-delete days means approximately
14 bundles; 30 live snapshot days plus seven soft-delete days means 37
snapshots. Lifecycle deletion is asynchronous, so leave extra headroom.

```text
steady-state stored GiB ≈ 15 × R + 37 × S
monthly download GiB   ≈ 30 × R × full_restore_equivalents + site_deploys × S
                        + retries/bootstrap
storage cost           ≈ max(0, stored_GiB − remaining_free_GiB) × $0.020
```

For planning, `R = 1 GiB`, `S = 0.09 GiB`, and 30 site deploys give roughly
18.33 GiB stored and 32.7 GiB downloaded per month. Storage is about
$0.27/month if all 5 GiB of storage allowance is available, or $0.37 without
it; eligible transfer and bundle operations fit the free allowance when
unused elsewhere. Without free transfer, 32.7 GiB at $0.12/GiB costs about
$3.92 alone. Recheck shared allowance and actual compressed sizes before
enabling the schedule. This is a scenario, not the current invoice.
[Cloud Storage rates](https://cloud.google.com/storage/pricing)

For multiple jobs, account for every handoff: four full 1 GiB restores per
night plus 30 snapshot downloads would be 122.7 GiB/month, already above
the nominal 100 GB free allowance. Additional full checkpoint uploads also
multiply retained storage. Transfer only the source bundles needed by each
stage, measure total bytes across the entire workflow, and include staged
checkpoints in the budget. Free compute does not make repeated GCS restores
free. The single-bundle scenario above is not an estimate for four full
restores or four full checkpoint uploads per night.

The combined monthly forecast is **existing Firebase Hosting + existing
API/other charges + incremental storage/transfer**, with $0 Actions
compute. Do not call the total $0: current hosting traffic and billing
account usage have not been audited. Firebase Hosting includes 10 GB
storage and 360 MB/day transfer; excess Blaze usage is charged. Retained
hosting releases and visitor traffic need headroom too.
[Firebase pricing](https://firebase.google.com/pricing)

The parser enforces a 1 GiB limit on the total compressed source state and
a per-run restore budget equivalent to 50 GiB/month at 30 nights. Stage
handoffs count toward that budget; retries and other workflows still need
additional headroom. Each source directory is a separate bundle. It also
stores temporary database checkpoints, a final compressed SQLite file, and
private diagnostics (at most 10 MiB per stage/attempt). Include those in
retained-storage estimates; the simplified formula above excludes them.
Record compressed sizes, elapsed time, and peak memory on rehearsal runs.
If the total forecast exceeds $2, revisit retention and transfer before
activation; $10 is the absolute project ceiling, not the operating target.

## Terraform changes

- `infra/snapshot-storage.tf` imports the existing bucket into management,
  preserving its region, storage class, public access prevention, uniform
  access, and seven-day soft-delete window. It prevents Terraform destroy
  and disables forced deletion of contents. It scopes 30-day expiration
  to `snapshots/` and adds seven-day expiration for
  `parser-state/checkpoints/`. The seed and current manifest do not expire.
- `infra/nightly-parser.tf` creates `gha-nightly-parser` and binds it to
  `.github/workflows/nightly-parser.yml` on `main`, for `schedule` and
  `workflow_dispatch` only. It grants source-state reads, append-only
  checkpoints/snapshots, and replacement of exactly
  `parser-state/latest.json` and `parser-state/lock.json`. It can read
  snapshot metadata/content to recognize interrupted publication. Seed replacement and snapshot deletion are
  excluded. Object-name listing is bucket-wide because GCS IAM cannot
  prefix-filter that permission. This account has no Firebase Hosting role.
- `infra/github-deploy.tf` maps workflow, ref, and event claims for that
  binding. Existing deployer grants are preserved, including its current
  bucket-wide read access. The new account is separated by its grants;
  existing main-branch workflows can still assume the existing deployer.

The import block is declarative: a plan reads the existing bucket; only an
approved apply records the import and changes its lifecycle policy. Do not
create a replacement bucket or put Terraform state into the archive bucket.
Objects outside the two expiring prefixes will no longer expire, so review
existing object prefixes before applying. No bucket-wide IAM policy is
replaced. [GitHub OIDC claims](https://docs.github.com/en/actions/reference/security/oidc),
[Cloud Storage roles](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)

## Stages, contention, and recovery

`nightly-parser.yml` runs CI, then calls `parser-stage.yml` sequentially for
legislature, finance, community, federal, import, and enrichment. Each job
has 330 minutes including setup, restoration, and checkpoint upload; the
processing step has a five-hour deadline. A single stage that exceeds this
needs a smaller supported source/date boundary. There is no parallel
scraping and no reduction in source pacing.

Finance rebuilds the legislative database for committee matching. Its inputs
include historical session rosters and legacy service records, which are
required for historical attribution and the curated term-event checks.

Each job owns an isolated local SQLite file. Import finishes before
enrichment starts, and SQLite's backup API includes committed WAL writes in
the private handoff. The `.bill_counts.json` integrity baseline travels in
the manifest and is required on restore. No runner writes a shared SQLite
file, and site releases read only a completed, immutable snapshot.

The workflow concurrency group serializes runs; the generation-protected
GCS lock also covers cloud-writing `run.sh` executions. `run.sh --local`
retains its previous no-GCS behavior: coordinate those scrapes manually,
and never run two local imports against the same working database.

Checkpoints contain exact object generations and SHA-256 digests. Archives
reject traversal, links, special files, duplicate entries, oversized inputs,
and existing restore destinations. All collector output stays private;
bounded diagnostic tails are stored beside the checkpoint and expire after
seven days, followed by the existing seven-day soft-delete window. GCP
authentication is renewed after each processing step before uploads.

OpenStates jurisdiction filenames contain colons on Linux. Checkpoint
restores preserve those names on Linux while rejecting Windows drive paths
and, on Windows, colon names that could address alternate data streams.
Use Linux (including a Linux filesystem in WSL) to inspect these checkpoints.

For a failed run, rerun the failed jobs in GitHub, or manually dispatch the
workflow with `resume_run` set to the original numeric run ID. Completed
stages are reused. Resume requires the same source commit and the same
last-successful manifest generation; stale resumes fail. A new run on a
different commit starts with a blank `resume_run`. Interrupted partial
stages are rerun; only completed stages have reusable checkpoints.

Only a successful enrichment/integrity stage produces the final SQLite
snapshot. Publication copies that immutable candidate to `snapshots/` and
then advances `latest.json` with a generation precondition. A retry can
recognize a snapshot already copied before interruption. The two writes
are not atomic: a complete validated snapshot can be visible to deployment
before the source-state manifest advances. It never exposes a partial DB.

Locks are not automatically stolen. Normal success/failure cleanup releases
only its own lock. After cancellation or host failure, inspect the lock's
execution ID and confirm that execution has stopped before an operator
deletes **that generation**. Never remove a lock just because a job is slow.
If a checkpoint expires, restore fails; it does not silently fall back to
an older seed. Recover a reviewed baseline explicitly, preserving the bill
count baseline and the offline source archive.

## Bootstrap and activation

1. Apply the reviewed Terraform plan and set `GCP_PARSER_SA` from
   `nightly_parser_service_account`. Reuse `GCP_WIF_PROVIDER`. Configure
   the GitHub environment `nightly-parser` to allow `main` only. Keep
   `NIGHTLY_PARSER_ENABLED` unset until rehearsal succeeds.
2. In the trusted local checkout, verify a complete `_data/`, the upstream
   `_cache/`, and `data/.bill_counts.json`. Seed with an operator identity:

   ```bash
   cd pipeline
   uv run --locked python -m nightly seed --revision "$(git rev-parse HEAD)"
   ```

   The command compresses every source bundle and checks the combined
   1 GiB budget before uploading. It refuses to replace an existing current
   manifest. Keep the `.private/nightly-seed/` bundles and an offline archive
   copy; never commit or upload them as Actions artifacts. The parser
   service account deliberately cannot create or replace the seed.
3. Merge through normal required CI and code-owner review, then manually
   dispatch `nightly-parser.yml` on `main`. Check stage durations, source
   policies, private diagnostics, transferred bytes, and the final snapshot.
   A missing/changed source policy fails closed. Production hosting is not
   automatically released by this workflow.
4. After a successful rehearsal and combined cost review, set
   `NIGHTLY_PARSER_ENABLED=true`. The schedule is 05:15 `America/Chicago`.
   GitHub may delay/drop scheduled runs and disables public schedules after
   60 days without repository activity. Use GitHub failure notifications and
   inspect `latest.json`'s `completed_at` for freshness. Clear the variable
   to stop future scheduled collection; an in-flight run must be handled
   separately. [Scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Review and application

Run `tofu fmt -check -recursive`, `tofu init -backend=false`, and
`tofu validate` from `infra/` (Terraform equivalents also work). Save any
live plan under ignored `.private/`, outside Git:

```bash
tofu plan -out=../.private/nightly-parser.tfplan
```

Expect adoption of the existing bucket, a lifecycle update, the additional
WIF mapping, and the new parser identity/IAM grants. Investigate any
replacement, unrelated grant change, or API enablement before proceeding.
Apply requires a separately approved plan; applying the infrastructure
alone does not install the workflow, seed data, or schedule the parser.

The infrastructure apply completed on 2026-09-07: **1 bucket imported,
9 resources added, 2 updated, 0 destroyed**. The source seed and live
rehearsal are separate from that application.

The GitHub environment `nightly-parser` allows the `main` branch, the
`GCP_PARSER_SA` repository variable points to the applied identity, and
`NIGHTLY_PARSER_ENABLED=false`. Workflow files must reach `main` through
the normal review process before manual dispatch is available there.

Implementation validation on 2026-09-07: the full pipeline suite passed
(218 tests), including stage resume, stale-state rejection, lock ownership,
interrupted publication, safe extraction, and WAL backup. Ruff, workflow
guards, Terraform formatting, and Terraform validation passed. The pinned
scraper dependencies were installed for Linux and the CLI help command
started under Python 3.11 in WSL without fetching records. Live source
timing and cloud identity enforcement still require the rehearsal above.
