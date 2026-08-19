# site/

Astro + Tailwind + Pagefind static site, scaffolded properly in Phase 5.
Pages are pre-rendered at build time; `src/lib/db.ts` reads `data/wi.sqlite`
via better-sqlite3 during `astro build`. No servers, no client JS except
Pagefind and a tiny sort/filter helper.
