"""Ordered stages reuse the existing policy-checked collectors and importers."""

from pathlib import Path

# Bundle one directory at a time: jobs only download the inputs they use.
STATIC = ("sessions", "wec-results", "lobbying", "wiseye", "rosters", "districts", "ftm", "legacy")
DYNAMIC = ("wi", "people", "cfis", "subjects", "contacts", "federal", "local",
           "wec", "lrb_cache", "companions_cache", "scraper_cache")
SOURCES = STATIC + DYNAMIC
STAGES = ("legislature", "finance", "finance-receipts", "finance-audit", "finance-committees",
          "community", "federal", "import", "enrich")
READS = {
    "legislature": ("wi", "people", "scraper_cache"),
    # Committee matching rebuilds legislative history, including roster/term supplements.
    "finance": ("wi", "people", "sessions", "rosters", "legacy", "cfis"),
    "finance-receipts": ("cfis",),
    "finance-audit": ("cfis",),
    "finance-committees": ("cfis",),
    "community": ("people", "subjects", "contacts", "local"),
    "federal": ("federal",),
    "import": tuple(s for s in SOURCES
                    if s not in ("lrb_cache", "companions_cache", "scraper_cache")),
    "enrich": ("database", "wi", "sessions", "lrb_cache", "companions_cache"),
}
WRITES = {
    "legislature": ("wi", "people", "scraper_cache"),
    "finance": ("cfis",),
    "finance-receipts": ("cfis",),
    "finance-audit": ("cfis",),
    "finance-committees": ("cfis",),
    "community": ("subjects", "contacts", "local"),
    "federal": ("federal",),
    "import": ("wec", "database"),
    "enrich": ("lrb_cache", "companions_cache", "database"),
}


def commands(stage: str, root: Path, cycle: str, context: dict) -> list[list[str]]:
    if stage == "finance-month":
        month = context["month"]
        return [["scraper.fetch_cf_committees", "--since", month, "--until", month]]
    db = "../data/wi.sqlite"
    sessions = sorted(str(p.relative_to(root)) for p in (root / "_data/sessions").iterdir()
                      if p.is_dir()) if stage in ("finance", "import") else []
    if stage in ("finance", "import") and not sessions:
        raise ValueError("Historical sessions missing; restore a complete source seed")
    rebuild = ["importer.import_openstates", "_data/wi", *sessions, db]
    stages = {
        "legislature": [["scraper.scrape", "bills"], ["scraper.scrape", "events"],
                        ["scraper.fetch_people"], ["scraper.fetch_committees"]],
        "finance": [rebuild, ["scraper.fetch_cfis", "map", db]],
        "finance-receipts": [["scraper.fetch_cfis", "transactions",
                              "--as-of", context["finance_as_of"]]],
        "finance-audit": [["scraper.fetch_cfis", "audit", "--sample", "3",
                           "--as-of", context["finance_as_of"]]],
        "finance-committees": [["nightly.finance"]],
        # Bind retained profiles to archived members before refreshing office records.
        "community": [["scraper.fetch_subjects"], ["scraper.fetch_contacts", "--refresh"],
                      ["scraper.fetch_local_profiles"], ["scraper.fetch_local_votes"]],
        "federal": [["scraper.fetch_federal_votes"],
                    ["scraper.fetch_federal_finance", "--as-of", context["finance_as_of"]]],
        "import": [rebuild,
                   ["importer.wec_pdf", "_data/wec/ballot-access.pdf",
                    f"_data/wec/candidates-{cycle}.csv"],
                   ["importer.elections", db, "--cycle", cycle],
                   ["importer.import_wec", f"_data/wec/candidates-{cycle}.csv",
                    db, "--cycle", cycle],
                   ["importer.import_wec_results", "_data/wec-results", db],
                   ["importer.import_cfis", "_data/cfis", db],
                   ["importer.import_cf_committees", "_data/cfis", db],
                   ["importer.import_lobbying", "_data/lobbying", db],
                   ["importer.import_subjects", "_data/subjects", db],
                   ["importer.import_wiseye", "_data/wiseye/videos.json", db],
                   ["importer.import_contacts", "_data/contacts/contacts.json", db],
                   ["importer.import_federal", "_data/federal", db],
                   ["importer.federal_finance", "_data/federal", db],
                   ["importer.import_local", "_data/local", db]],
        "enrich": [["importer.enrich_lrb", db], ["importer.enrich_companions", db],
                   ["importer.checks", db]],
    }
    return stages[stage]
