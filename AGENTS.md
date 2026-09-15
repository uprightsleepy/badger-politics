# Repository Guidelines

## Agent skills

Automatically select the relevant installed skills for each task. Read their `SKILL.md` before applying them and briefly name the selection. Use the current session's skill catalog to resolve paths; Matt Pocock's standalone skills live under `$CODEX_HOME/skills` (normally `~/.codex/skills`), and native plugins expose namespaced skills. If an installation is unavailable, report that once and continue with the applicable repository guidance.

### Task routing

| Task | Use |
| --- | --- |
| Start development work | `superpowers:using-superpowers` to select the applicable workflow. |
| Design a feature with unresolved requirements | `superpowers:brainstorming`; use Matt's `domain-modeling` for project terminology and `prototype` when an experiment can settle a design question. |
| Implement an agreed multi-step change | `superpowers:writing-plans`, then `superpowers:executing-plans`; use `superpowers:using-git-worktrees` when isolation is needed. |
| Add or change tested behavior | `superpowers:test-driven-development`; use Matt's `tdd` instead when following his `implement` workflow. |
| Investigate a bug or failing test | `superpowers:systematic-debugging`; use Matt's `diagnosing-bugs` instead for difficult intermittent bugs or performance regressions that need instrumentation and minimization. |
| Design module boundaries or refactor architecture | Matt's `codebase-design` and, when vocabulary or domain rules change, `domain-modeling`. |
| Investigate an engineering question | Matt's `research`, using primary sources and the repository's source-access rules. |
| Review a diff against requirements and standards | Matt's `code-review`; use `superpowers:requesting-code-review` for review within a Superpowers execution workflow, and `superpowers:receiving-code-review` when addressing feedback. |
| Resolve an existing merge or rebase conflict | Matt's `resolving-merge-conflicts`. |
| Write agent instructions | Matt's `writing-for-agents`. |
| Implement, refactor, design, or select dependencies | Also apply `ponytail:ponytail`: understand the affected flow, reuse existing code, and prefer standard-library or native features before new dependencies. |
| Review unnecessary complexity | `ponytail:ponytail-review` for a diff; `ponytail:ponytail-audit` for an explicitly requested repository-wide audit; `ponytail:ponytail-debt` for deferred `ponytail:` shortcuts. |
| Finish implementation or a fix | `superpowers:verification-before-completion`; use `superpowers:finishing-a-development-branch` when branch delivery is in scope. |

Choose one primary workflow for each phase; carry its existing design, plan, and test evidence forward. Complement it with focused skills instead of repeating competing planning, debugging, TDD, or review workflows. Scale the process to the task: clear, small edits can proceed directly; unresolved consequential choices need clarification. Documentation-only changes need document checks, not application tests.

For work-in-progress reviews, inspect staged, unstaged, and relevant untracked files alongside the committed diff; Matt's `code-review` commit range alone does not include them.

Matt's orchestration skills (`ask-matt`, `grill-with-docs`, `grill-me`, `triage`, `improve-codebase-architecture`, `to-spec`, `to-tickets`, `implement`, `wayfinder`, `handoff`, `teach`, `to-questionnaire`, `wait-what`, and `setup-matt-pocock-skills`) are user-invoked upstream. Use them when the user requests that workflow; select their reusable model-invoked skills automatically for ordinary tasks. Use `wizard` when a requested setup needs human-only steps. Ponytail's `ponytail-help` and `ponytail-gain` answer requests about its commands and benchmark results.

### Project configuration and precedence

- Issue drafts and plans default to ignored local files; read `docs/agents/issue-tracker.md` before using ticket/spec workflows. Follow an explicitly supplied GitHub issue or requested tracker instead when applicable.
- Read `docs/agents/triage-labels.md` before triage and `docs/agents/domain.md` before domain modeling or architectural exploration.
- Keep raw plans, research, and audit output under `.private/`, including when a skill suggests `docs/plans/`, `docs/superpowers/`, or `.scratch/`. Reviewed, public-safe documentation follows the existing repository rules.
- The user's instructions and this repository's correctness, source-access, privacy, cost, and release rules govern plugin use. Simplicity must preserve requested behavior, integrity checks, validation, error handling, security, and accessibility. Preserve existing user changes.
- Skill routing does not authorize publishing, messaging others, merging, deploying, discarding work, or destructive cleanup. Use existing task authorization for those actions. Use subagent workflows only when requested by the user or required by the selected applicable skill, and when the host permits them.
- Apply the relevant skill directly even when optional lifecycle hooks are inactive. Respect explicit requests to disable a workflow or Ponytail mode.

Installation sources and maintenance notes: `docs/agents/integrations.md`.

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

Prefer self-documenting code and simple, sparse comments. Keep explanations of political processes and non-obvious correctness constraints.

## Testing Guidelines

Name pytest files `test_*.py` and functions `test_*`; cover changed parsing, attribution, and integrity behavior. No numeric coverage threshold is configured. After building, run `node scripts/<name>.mjs` from `site/` for `preflight`, `verify`, `a11y`, `responsive`, and `links`. Browser checks use Puppeteer/axe-core and Chrome/Edge (`BROWSER_PATH` override); accessibility requires zero violations.

Run `npm run test:harness` from `site/` for readiness and timing regressions (`scripts/tests/*.test.mjs`); Windows timing tests require WSL with GNU time.

## Commit & Pull Request Guidelines

History uses descriptive, sentence-style subjects without mandatory prefixes. Explain the behavior changed. Target `main`; include rationale, validation, related issues, and screenshots for visual changes. Code-owner approval and green CI are required.

## Data & Release Rules

Preserve static serving, SQLite-only storage, verified attribution, and provenance filtering. Never weaken integrity gates. Keep secrets in ignored `.env` files. Never overlap scrapes or build during database imports. Releases use GitHub Actions; follow `docs/deploys.md`.

Keep total infrastructure costs below $10/month excluding domains; prefer $0–5 and improvements without added recurring charges. Estimate combined hosting, storage, ingestion and API costs before adding paid services, leaving headroom for usage spikes.

This repository is public. Keep sent correspondence, personal contact details, raw working drafts, credentials, and audit output outside Git or under ignored `.private/`. Publish redacted templates and use the project contact URL in scripts. Use documented civic buildings for address examples. Review staged files before committing; CI scans history and tracked content for secrets.

## Scraping & Source Access Rules

Before adding or changing data gathering, review each source's current `robots.txt`, terms, API policies, and published access restrictions. Record policy URLs, review date, relevant constraints, and the host, paths, and use they govern. Public collection may proceed when no applicable explicit restriction prohibits it; missing policies or silence about scraping do not require affirmative permission. Prefer documented public APIs or official bulk downloads. An officially documented public API is an acceptable collection route without a separate permission request; follow its documented scope, authentication requirements, usage limits, and applicable explicit restrictions. Do not extend a website restriction to a separate API without evidence that it applies.

Respect disallowed paths, crawl delays, rate limits, and retry instructions; use an identifying User-Agent, caching, and backoff. Do not bypass access controls or explicit restrictions. Resolve conflicts between applicable explicit rules before using the affected route. Distinguish policy prohibitions from failed policy checks, technical access denials, and unverified data formats; a failed request alone is not a published prohibition. Keep runtime denial protections and reviewed source scopes in place.
