"""Split collection matches an unsplit import on identical frozen source pages."""

import copy
import json
from datetime import date

import pytest

from importer.import_cf_committees import run as import_committees
from importer.import_cfis import run as import_receipts
from nightly.finance import merge_months, months_for
from scraper import cfis_api
from scraper import fetch_cf_committees as collector


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def baseline(path):
    write(path / "committees.json", [
        {"entity_id": 99, "name": "Archived Committee", "committee_type": "PAC",
         "assigned_id": "A99"},
    ])
    write(path / "pac-2024-12.json", [
        {"id": 99, "filer_entity_id": 99, "direction": "INCOMING", "date": "2024-12-31",
         "amount": 12.25, "filer_type": "PAC"},
    ])
    # This month contains stale values, and a row the source has since removed.
    write(path / "pac-2025-01.json", [
        {"id": 1, "filer_entity_id": 10, "date": "2025-01-01", "amount": 1},
        {"id": 88, "filer_entity_id": 10, "date": "2025-01-02", "amount": 88},
    ])
    write(path / "committee_map.json", [
        {"person_id": "p1", "entity_id": 20, "committee": "Verified Candidate Committee"},
    ])
    for month in ("2024-12", "2025-01"):
        write(path / f"tx-{month}.json", [
            {"id": int(month.replace("-", "")), "person_id": "p1", "committee_entity_id": 20,
             "date": month + "-01", "amount": 20, "from_name": "Example Donor",
             "from_type": "Individual", "occupation": "Teacher", "category": "Monetary"},
        ])


def raw_transaction(key, when, *, name="Example PAC", candidate=False, stance=None):
    entity = {"id": 10, "name": name, "committee": {
        "committeeType": {"name": "State Candidate" if candidate else "PAC"},
        "assignedCommitteeId": "P10",
    }}
    return {"id": key, "date": when, "amount": 125.50 + key, "createdByEntityId": 10,
            "createdByEntity": entity, "from_entity": {"id": 30, "name": "Example Source"},
            "transactionType": {"direction": "INCOMING"}, "supportStance": stance,
            "reports": [{"id": 100 + key, "name": "Filed Report"}]}


def test_split_and_unsplit_archives_and_database_are_identical(tmp_path, monkeypatch, make_db):
    pages = [raw_transaction(1, "2025-01-01T00:00:00Z"),
             raw_transaction(2, "2025-01-31T23:59:59Z"),
             raw_transaction(3, "2025-01-31T23:59:59Z", candidate=True),
             raw_transaction(4, "2025-02-01T00:00:00Z", name="Updated PAC"),
             raw_transaction(5, "2025-02-28T23:59:59Z", name="Updated PAC", stance="FOR")]
    calls = []

    def api(http, procedure, payload, **kwargs):
        assert procedure == "publicFrontendApi.getTransactions"
        assert payload["dateTo"].endswith("T23:59:59")
        calls.append(copy.deepcopy(payload))
        selected = [row for row in pages
                    if payload["dateFrom"] <= row["date"][:10] <= payload["dateTo"][:10]]
        return {"results": copy.deepcopy(selected[payload["skip"]:
                                                  payload["skip"] + payload["take"]])}

    monkeypatch.setattr(cfis_api, "call", api)
    monkeypatch.setattr(cfis_api, "PAGE", 2)
    monkeypatch.setattr(collector, "PAGE", 2)
    monkeypatch.setattr(collector, "session", lambda: object())
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    unsplit, split, inputs = tmp_path / "unsplit", tmp_path / "split", tmp_path / "months"
    baseline(unsplit)
    baseline(split)
    monkeypatch.setattr(collector, "DATA_DIR", unsplit)
    collector.main(["--since", "2025-01", "--until", "2025-02"])
    unsplit_calls = copy.deepcopy(calls)
    calls.clear()
    for month in ("2025-02", "2025-01"):
        monkeypatch.setattr(collector, "DATA_DIR", inputs / month / "cfis")
        collector.main(["--since", month, "--until", month])
    assert sorted(calls, key=lambda p: (p["dateFrom"], p["skip"])) == unsplit_calls
    merge_months(split, inputs, ["2025-01", "2025-02"])
    assert {p.name for p in split.iterdir()} == {p.name for p in unsplit.iterdir()}
    for path in unsplit.iterdir():
        assert json.loads(path.read_text()) == json.loads((split / path.name).read_text())
    outputs = []
    for source in (unsplit, split):
        db_path = source / "result.sqlite"
        db = make_db(db_path)
        db.execute("INSERT INTO people (id, name) VALUES ('p1', 'Example Legislator')")
        db.commit()
        import_committees(source, db_path)
        import_receipts(source, db_path)
        outputs.append({table: db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                        for table in ("cf_transactions", "cf_committees", "contributions",
                                      "cfis_committees")})
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert {row[0] for row in db.execute("SELECT id FROM cf_transactions")} == {1, 2, 4, 5, 99}
        db.close()
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("problem", ["missing_month", "duplicate_id", "wrong_month", "registry"])
def test_invalid_batch_leaves_archive_untouched(tmp_path, problem):
    archive, inputs = tmp_path / "archive", tmp_path / "months"
    baseline(archive)
    before = {p.name: p.read_bytes() for p in archive.iterdir()}
    for month in ("2025-01", "2025-02"):
        write(inputs / month / "cfis" / f"pac-{month}.json", [
            {"id": int(month[-2:]), "date": month + "-01", "amount": 25},
        ])
        write(inputs / month / "cfis/committees.json", [])
    if problem == "missing_month":
        (inputs / "2025-02/cfis/pac-2025-02.json").unlink()
    elif problem == "duplicate_id":
        write(inputs / "2025-02/cfis/pac-2025-02.json", [{"id": 1, "date": "2025-02-01"}])
    elif problem == "wrong_month":
        write(inputs / "2025-02/cfis/pac-2025-02.json", [{"id": 2, "date": "2025-03-01"}])
    else:
        write(inputs / "2025-02/cfis/committees.json", {})
    with pytest.raises(ValueError):
        merge_months(archive, inputs, ["2025-01", "2025-02"])
    assert {p.name: p.read_bytes() for p in archive.iterdir()} == before


def test_plan_covers_year_boundary_and_refuses_truncation():
    assert months_for({"finance_as_of": "2026-01-01"}) == [
        *(f"2025-{month:02}" for month in range(1, 13)), "2026-01",
    ]
    with pytest.raises(ValueError, match="job count"):
        months_for({"finance_as_of": "2050-01-01"})


def test_receipt_refresh_and_audit_use_frozen_date(tmp_path, monkeypatch):
    from scraper import fetch_cfis

    windows = []
    audited = []
    monkeypatch.setattr(fetch_cfis, "load_committee_ids", lambda: {})
    monkeypatch.setattr(fetch_cfis, "session", lambda: object())
    monkeypatch.setattr(fetch_cfis, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_cfis.time, "sleep", lambda _: None)

    def fetch(http, ids, first, last, label, attempts):
        windows.append((first, last))
        return [], 0, 0, set(), True

    monkeypatch.setattr(fetch_cfis, "_fetch_with_retries", fetch)
    fetch_cfis.fetch_transactions("2025-01", date(2025, 2, 28))
    assert windows == [("2025-01-01", "2025-01-31T23:59:59"),
                       ("2025-02-01", "2025-02-28T23:59:59")]
    for month in range(1, 13):
        write(tmp_path / f"tx-2024-{month:02}.json", [])

    def audit(http, ids, first, last):
        audited.append(first)
        return [], 0, 0, set()

    monkeypatch.setattr(fetch_cfis, "fetch_window", audit)
    fetch_cfis.audit_archives(3, date(2025, 2, 28))
    expected = audited.copy()
    audited.clear()
    fetch_cfis.audit_archives(3, date(2025, 2, 28))
    assert audited == expected and len(audited) == 3
