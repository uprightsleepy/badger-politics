# Repository Guidelines

## Project Structure & Module Organization

Badger Politics converts official records into SQLite and an Astro static site.
- `pipeline/scraper/` fetches records; `importer/` contains transformations, curation JSON, `schema.sql`, and integrity checks; `dataproducts/` builds exports.
- `pipeline/tests/` contains Python tests. Keep upstream scraper fixes in `pipeline/patches/`; do not edit `pipeline/vendor/` directly.
- `site/src/` holds pages, components, layouts, browser scripts, and shared libraries. Use `src/lib/db.ts` for database access. Assets live in `site/public/`; browser checks live in `site/scripts/`.
- `infra/` contains OpenTofu; `.github/workflows/` defines CI/releases; `docs/` holds methodology and runbooks. Raw archives (`pipeline/_data/`) and `data/wi.sqlite` are gitignored.

## Build, Test, and Development Commands

Use Python 3.11+, uv, and Node 22. Site development requires `data/wi.sqlite`.

From `pipeline/`:
- `uv sync --locked`: install pinned dependencies.
- `uv run pytest`: run unit/regression tests.
- `uv run ruff check .`: lint Python.
- `uv run python -m importer.checks ../data/wi.sqlite`: validate data integrity.

From `site/`:
- `npm ci --ignore-scripts`, then `npm rebuild better-sqlite3`: install dependencies and build the native database module.
- `npm run dev`: start local development.
- `npm run build`: build the current biennium and Pagefind index; set `BUILD_SESSIONS=all` for history.
- `npx astro check`: check Astro/TypeScript.
- `npm run preview`: preview the build.

## Coding Style & Naming Conventions

Use four-space Python indentation, snake_case functions/modules, and Ruff's 100-character limit and import sorting. Follow existing TypeScript/Astro style: two-space indentation, double quotes, semicolons, camelCase helpers, and PascalCase components. No site formatter is configured. Validate infrastructure with `tofu fmt -check -recursive` and `tofu validate`.

## Testing Guidelines

Name pytest files `test_*.py` and functions `test_*`; cover changed parsing, attribution, and integrity behavior. No numeric coverage threshold is configured. After building, run `node scripts/<name>.mjs` from `site/` for `preflight`, `verify`, `a11y`, `responsive`, and `links`. Browser checks use Puppeteer/axe-core and Chrome/Edge (`BROWSER_PATH` override); accessibility requires zero violations.

Run `npm run test:harness` from `site/` for readiness and timing regressions (`scripts/tests/*.test.mjs`); Windows timing tests require WSL with GNU time.

## Commit & Pull Request Guidelines

History uses descriptive, sentence-style subjects without mandatory prefixes. Explain the behavior changed. Target `main`; include rationale, validation, related issues, and screenshots for visual changes. Code-owner approval and green CI are required.

## Data & Release Rules

Preserve static serving, SQLite-only storage, verified attribution, and provenance filtering. Never weaken integrity gates. Keep secrets in ignored `.env` files. Never overlap scrapes or build during database imports. Releases use GitHub Actions; follow `docs/deploys.md`.

## Scraping & Source Access Rules

Before adding or changing data gathering, review and follow each source site's current `robots.txt`, terms of use, API policies, and published access restrictions. Record policy URLs, review date, and relevant constraints in scraper documentation. Respect disallowed paths, crawl delays, rate limits, and retry instructions; use an identifying User-Agent, caching, and backoff. Do not bypass access controls or scraping restrictions. If rules are unclear or conflict, pause collection from that source until clarified; prefer a permitted official API or bulk download.
