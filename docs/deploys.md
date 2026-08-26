# Deploys

The site is released by GitHub Actions from a commit on `main`. Nothing is
published from a laptop.

## Why it works this way

A Firebase Hosting release replaces the *entire* site. There is no partial
upload and no merge: whatever is in `site/dist` at deploy time becomes the
whole of badgerpolitics.org. That makes two ordinary mistakes destructive.

1. **A partial build.** `npm run build` defaults to two sessions, because a
   full build is slow to iterate on. Production needs `BUILD_SESSIONS=all`.
   Deploying a default build removes roughly 38,000 pages, and nothing in
   the build output says which kind you got.
2. **Deploying uncommitted work.** Deploying from a working copy publishes
   whatever happened to be on disk, which may include half-finished edits
   and will not match any commit you can point at afterwards.

Both are now structurally impossible rather than merely discouraged: CI
builds from a checkout of the commit, and `scripts/preflight.mjs` refuses to
release a build that does not match the database that produced it.

## What runs, and when

| Trigger | Workflow | What happens |
| --- | --- | --- |
| Pull request | `ci.yml` | Ruff, pytest, schema applies, site typecheck, workflow guards, `tofu validate`. No secrets, no deploy. |
| Push to `main` touching `site/**` | `deploy.yml` | Build → preflight → verify → release to prod → smoke-test the live URL. |
| Manual (`workflow_dispatch`) | `deploy.yml` | Same, with a choice of dev or prod. |
| Nightly (Cloud Run, pending) | `pipeline/run.sh` | Scrape → import → checks → build → preflight → deploy → snapshot. |

## The gates, in order

`deploy.yml` runs these before anything is published. Each one has to pass.

1. **Database integrity** — `PRAGMA quick_check` plus a floor on the bill
   count. A truncated download still produces a file; only a query proves
   the file is a database.
2. **Preflight** (`site/scripts/preflight.mjs`) — asserts the built tree
   against the database it was built from: every session present, one page
   per bill, per legislator and per roll call, a search index at least as
   large as the bill count, the landing pages present, and the independence
   disclaimer on the homepage. It derives its expectations from the data,
   so it never needs updating when the counts change.
3. **Site verification** — `links`, `responsive`, `a11y`, `verify`.
4. **Post-release smoke test** — hits the public URL, asserts 200s, and
   checks that HTML is still served with `must-revalidate`. A page cached
   for an hour once hid a broken deploy for exactly that long.

## Credentials

There is no service-account key anywhere. GitHub Actions federates into
`gha-site-deployer@badgerpolitics-prod.iam.gserviceaccount.com` through
Workload Identity, with two conditions on the trust:

- the token's `repository` claim must be `uprightsleepy/badger-politics`
- the token's `ref` claim must be `refs/heads/main`

A pull request runs with `refs/pull/N/merge`, so it cannot assume the
identity even from inside this repository. The service account holds
`firebasehosting.admin` on the prod project and *read-only* access to the
snapshot bucket, so a compromised run can publish a site but cannot alter
or delete the database.

Two repository variables wire it up. They are not secrets — the conditions
above are what make the identity safe, not the obscurity of these values:

- `GCP_WIF_PROVIDER` — full provider resource name
- `GCP_DEPLOY_SA` — deployer service account email

One optional secret: `LOGO_DEV_TOKEN`. Without it the build still succeeds
and organisations fall back to monogram tiles.

## Where the data comes from

CI does not scrape. It downloads the newest `*.sqlite.gz` from
`gs://badgerpolitics-prod-snapshots/snapshots/`, which the nightly job
writes. Snapshots are gzipped because the database is 397 MB raw and about
90 MB compressed; at one download per deploy, uncompressed egress alone
would consume most of the ~$2/month ceiling. The runner also caches the
snapshot by filename, so several deploys in a day pay for one download.

This means **a deploy publishes the data as of the last nightly snapshot**,
not as of the moment you deploy. Site changes go out immediately; data
changes wait for the next snapshot.

## Rolling back

Hosting keeps previous versions:

```bash
npx firebase-tools@14 hosting:rollback --project badgerpolitics-prod
```

That reverts the serving version immediately. Follow it with a revert
commit, or the next deploy will republish the bad build.

## Running a deploy by hand

Still supported, and still gated — `run.sh` runs preflight too:

```bash
cd pipeline && FB_PROJECT=badgerpolitics-prod ./run.sh
```

`run.sh` defaults to `badgerpolitics-dev`, so promoting to production is
always an explicit act.
