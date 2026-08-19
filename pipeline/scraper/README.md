# scraper/

Thin wrapper around [openstates-scrapers](https://github.com/openstates/openstates-scrapers)
(`wi` scrapers), implemented in Phase 1.

GPL boundary: openstates-scrapers is GPL-3.0. It is used ONLY as a pinned
dependency invoked via its CLI (`os-update wi bills --scrape`). Its modules are
never imported into this Apache-2.0 codebase, and its code is never copied
in-tree. Local patches, if ever needed, live in `pipeline/patches/` with
documented upstream-PR intent.
