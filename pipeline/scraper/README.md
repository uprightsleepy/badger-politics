# scraper/

Thin wrappers around external data sources. openstates-scrapers (GPL-3.0)
is pinned as a submodule and only ever invoked via its CLI (`os-update`);
its modules are never imported and its code never copied in-tree. Runtime
patches live in `pipeline/patches/` (see its README for upstream intent)
and are applied by `scrape.py` before every run.
