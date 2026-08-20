# site/

Astro + Tailwind + Pagefind static site. Pages are pre-rendered at build
time; `src/lib/db.ts` reads `../data/wi.sqlite` via better-sqlite3 during
`astro build`. Client JS is kept small and dependency-free: Pagefind search,
the district/polling-place lookup, roll-call pinning, the month calendar,
and two tiny filter helpers.

`node scripts/verify.mjs` runs the headless-browser acceptance checks
against a built `dist/`.
