import io
import json
import sqlite3
import zipfile

import pytest

from importer.federal_finance import candidate_ids, cents, import_summaries, parse_summary
from importer.import_cf_committees import run as import_committees
from scraper import fetch_cf_committees as collector


def zipped(*records):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("weball26.txt", "\n".join("|".join(r) for r in records))
    return output.getvalue()


def record():
    values = [""] * 30
    values[0], values[1], values[18], values[27] = (
        "H0WI07101", "EXAMPLE, PAT", "WI", "07/22/2026")
    values[5], values[6], values[17], values[28] = "100.01", "20.00", "-1.25", "0.00"
    return values


def test_fec_money_keeps_cents_blanks_transfers_refunds_and_identity():
    row, = parse_summary(zipped(record()), {"H0WI07101": "T000165"}, 2026)
    assert row["receipts"] == 10001
    assert row["transfers_in"] == 2000
    assert row["individual_contributions"] == -125
    assert row["individual_refunds"] == 0
    assert row["cash_end"] is None
    assert row["coverage_end"] == "2026-07-22"
    assert row["bioguide"] == "T000165"
    assert parse_summary(zipped(record()), {"H8WI01156": "S001213"}, 2026) == []
    for raw in ["NaN", "Infinity", "1.001", "not money"]:
        with pytest.raises(ValueError):
            cents(raw)
    with pytest.raises(ValueError, match="duplicate"):
        parse_summary(zipped(record(), record()), {"H0WI07101": "T000165"}, 2026)
    wrong = record()
    wrong[27] = "12/31/2024"
    with pytest.raises(ValueError, match="outside"):
        parse_summary(zipped(wrong), {"H0WI07101": "T000165"}, 2026)


def test_fec_roster_uses_current_chamber_ids_and_rejects_ambiguity():
    roster = [{"terms": [{"state": "WI", "type": "rep"}],
               "id": {"bioguide": str(i), "fec": [f"H0WI{i:05d}"]}} for i in range(10)]
    roster[0]["terms"][0]["type"] = "sen"
    roster[0]["id"]["fec"].append("S0WI00000")
    assert "H0WI00000" not in candidate_ids(roster)
    roster[1]["id"]["fec"].append("H0WI11111")
    with pytest.raises(ValueError, match="Ambiguous"):
        candidate_ids(roster)


def test_fec_download_scope_allows_only_reviewed_summary_and_mirror():
    from scraper.source_access import SourceAccess, SourceAccessError
    access = SourceAccess(use_report=False)
    mirror = "cg-519a459a-0ea3-42c2-b7bc-fa1143481f74.s3-us-gov-west-1.amazonaws.com"
    access.source("https://www.fec.gov/files/bulk-downloads/2026/weball26.zip")
    access.source(f"https://{mirror}/bulk-downloads/2026/weball26.zip")
    with pytest.raises(SourceAccessError):
        access.source(f"https://{mirror}/unreviewed/file.zip")
    with pytest.raises(SourceAccessError):
        access.source("https://other.s3.amazonaws.com/bulk-downloads/2026/weball26.zip")


def test_fec_failed_refresh_rolls_back_existing_data(tmp_path):
    from importer.federal_finance import fec_url
    db_path = tmp_path / "db.sqlite"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE federal_members (bioguide TEXT)")
        db.execute("INSERT INTO federal_members VALUES ('T000165')")
    row, = parse_summary(zipped(record()), {"H0WI07101": "T000165"}, 2026)
    doc = {"cycle": 2026, "source_url": fec_url(2026), "fetched_at": "2026-09-09T00:00:00Z",
           "identities": {"H0WI07101": "T000165"}, "rows": [row]}
    archive = tmp_path / "finance-2026.json"
    archive.write_text(json.dumps(doc))
    import_summaries(tmp_path, db_path)
    doc["rows"][0]["bioguide"] = "WRONG"
    archive.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="identity"):
        import_summaries(tmp_path, db_path)
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT bioguide, receipts FROM federal_finance").fetchall() == [
            ("T000165", 10001)]
        from importer.checks import check_campaign_finance
        assert check_campaign_finance(db) == []
        db.execute("UPDATE federal_finance SET receipts=1.01")
        assert "integer cents" in check_campaign_finance(db)[0]


def test_state_campaign_reuses_scan_without_changing_existing_money(tmp_path, monkeypatch, make_db):
    from test_nightly_finance import raw_transaction
    source = raw_transaction(1, "2026-01-31T23:59:59Z",
                             name="Tiffany for Wisconsin", candidate=True)
    source["createdByEntityId"] = source["createdByEntity"]["id"] = 16621
    source["createdByEntity"]["committee"]["assignedCommitteeId"] = "0104212"
    pac = raw_transaction(2, "2026-01-15T00:00:00Z")
    monkeypatch.setattr(collector, "transaction_count", lambda *_: 2)
    monkeypatch.setattr(collector, "transaction_pages", lambda *_, **kw: iter([[source, pac]]))
    monkeypatch.setattr(collector, "session", lambda: object())
    monkeypatch.setattr(collector.time, "sleep", lambda _: None)
    monkeypatch.setattr(collector, "DATA_DIR", tmp_path)
    collector.main(["--since", "2026-01", "--until", "2026-01"])
    db_path = tmp_path / "db.sqlite"
    db = make_db(db_path)
    db.close()
    import_committees(tmp_path, db_path)
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT id FROM cf_transactions").fetchall() == [(2,)]
        assert db.execute("SELECT id FROM state_campaign_transactions").fetchall() == [(1,)]
        assert db.execute("SELECT * FROM state_campaign_coverage").fetchall() == [
            (16621, "2026-01")]
    source["createdByEntity"]["committee"]["assignedCommitteeId"] = "OTHER"
    with pytest.raises(ValueError, match="identity changed"):
        collector.fetch_month(object(), "2026-01-01", "2026-01-31T23:59:59")
