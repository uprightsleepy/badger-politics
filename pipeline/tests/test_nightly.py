"""Offline storage/protocol tests. No live scraping or cloud writes."""

import copy
import hashlib
import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from check_workflows import validate
from nightly.__main__ import run_stage
from nightly.archive import pack, unpack
from nightly.export_scraper_lock import export
from nightly.finance import merge_months, months_for
from nightly.month import MonthRunner
from nightly.runner import LATEST, LOCK, Runner, seed, source_path
from nightly.stages import SOURCES, STAGES, WRITES
from nightly.storage import GCS, Conflict, StorageError

REV = "a" * 40


class Store:
    def __init__(self):
        self.objects = {}
        self.serial = 0
        self.fail_latest = False

    def metadata(self, name):
        if name not in self.objects:
            raise FileNotFoundError(name)
        return self.objects[name][1]

    def upload(self, name, path, generation="0"):
        current = self.objects.get(name, (None, {"generation": "0"}))[1]
        if current["generation"] != generation:
            raise Conflict(name)
        self.serial += 1
        data = path.read_bytes()
        ref = {"object": name, "generation": str(self.serial), "bytes": len(data),
               "sha256": hashlib.sha256(data).hexdigest()}
        self.objects[name] = (data, ref)
        return ref

    def put_json(self, name, doc, scratch, generation="0"):
        if name == LATEST and self.fail_latest:
            raise StorageError("interrupted after snapshot creation")
        path = scratch / "upload.json"
        path.write_text(json.dumps(doc))
        return self.upload(name, path, generation)

    def read_json(self, name):
        meta = self.metadata(name)
        return json.loads(self.objects[name][0]), meta["generation"]

    def download(self, ref, target):
        meta = self.metadata(ref["object"])
        if meta["generation"] != ref["generation"] or meta["sha256"] != ref["sha256"]:
            raise StorageError("bad digest/generation")
        target.write_bytes(self.objects[ref["object"]][0])

    def copy(self, ref, name):
        data, _ = self.objects[ref["object"]]
        if name not in self.objects:
            self.serial += 1
            self.objects[name] = (data, {**ref, "object": name, "generation": str(self.serial)})
        assert self.objects[name][1]["sha256"] == ref["sha256"]
        return self.objects[name][1]

    def delete(self, name, generation):
        if self.metadata(name)["generation"] != generation:
            raise Conflict(name)
        del self.objects[name]


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 3, 31, 23, 59, tzinfo=UTC)

    monkeypatch.setattr("nightly.runner.datetime", Clock)
    root = tmp_path / "seed/pipeline"
    root.mkdir(parents=True)
    for name in SOURCES:
        path = source_path(root, name)
        path.mkdir(parents=True)
        (path / "sample.txt").write_text("private source content")
    (root / "_data/cfis/committees.json").write_text("[]")
    (root.parent / "data").mkdir()
    (root.parent / "data/.bill_counts.json").write_text('{"2025": 100}')
    store = Store()
    seed(store, root, tmp_path / "scratch", REV)
    return store


def runner(tmp_path, store, stage="legislature", run_id="123", execution="123-1"):
    root = tmp_path / f"{run_id}-{execution}-{stage}" / "pipeline"
    root.mkdir(parents=True, exist_ok=True)
    return Runner(store, root, run_id, REV, execution)


def complete(r, stage):
    if stage == "finance-committees":
        doc = json.loads(r.context.read_text())
        months = months_for(doc)
        merge_months(r.root / "_data/cfis", r.scratch / "finance-months", months)
        (r.scratch / "finance-complete.json").write_text(json.dumps({
            "run_id": r.run_id, "revision": r.revision, "months": months,
        }))
    for name in WRITES[stage]:
        if name == "database":
            (r.root.parent / "data").mkdir(exist_ok=True)
            with sqlite3.connect(r.root.parent / "data/wi.sqlite") as db:
                db.execute("CREATE TABLE IF NOT EXISTS probe(value)")
                db.execute("INSERT INTO probe VALUES ('complete')")
        else:
            source_path(r.root, name).mkdir(parents=True, exist_ok=True)
    (r.scratch / "success.json").write_text(json.dumps({
        "stage": stage, "revision": REV, "execution": r.execution,
    }))
    r.checkpoint(stage)


def complete_all(tmp_path, store):
    last = None
    for stage in STAGES:
        if stage == "finance-committees":
            for month in months_for(last.finance_plan()):
                monthly = month_runner(tmp_path, store, month)
                monthly.restore("finance-month")
                complete_month(monthly)
        last = runner(tmp_path, store, stage)
        last.acquire()
        assert last.restore(stage)
        complete(last, stage)
    return last


def month_runner(tmp_path, store, month, execution="123-1"):
    root = tmp_path / f"{execution}-{month}" / "pipeline"
    root.mkdir(parents=True, exist_ok=True)
    return MonthRunner(store, root, "123", REV, execution, month=month)


def complete_month(r):
    source = r.root / "_data/cfis"
    (source / f"pac-{r.month}.json").write_text("[]")
    (source / "committees.json").write_text("[]")
    (r.scratch / "success.json").write_text(json.dumps(r.receipt("finance-month")))
    r.checkpoint("finance-month")


def prepare_finance(tmp_path, store):
    for stage in ("legislature", "finance", "finance-receipts", "finance-audit"):
        r = runner(tmp_path, store, stage)
        r.acquire()
        r.restore(stage)
        complete(r, stage)
    return r


def test_lock_excludes_other_runs_and_wrong_release(tmp_path, seeded):
    first = runner(tmp_path, seeded)
    first.acquire()
    other = runner(tmp_path, seeded, run_id="456", execution="456-1")
    with pytest.raises(Conflict):
        other.acquire()
    other.release()
    assert seeded.read_json(LOCK)[0]["execution"] == "123-1"
    first.release()
    other.acquire()


def test_completed_stage_resume_skips_collection_and_new_revision_rejected(tmp_path, seeded):
    first = runner(tmp_path, seeded)
    first.acquire()
    first.restore("legislature")
    complete(first, "legislature")
    first.release()
    retry = runner(tmp_path, seeded, execution="123-2")
    retry.acquire()
    assert retry.restore("legislature") is False
    retry.revision = "b" * 40
    with pytest.raises(ValueError, match="exact source revision"):
        retry.restore("legislature")


@pytest.mark.skipif(os.name == "nt", reason="OpenStates colon filenames require a POSIX filesystem")
def test_checkpoint_handoff_preserves_openstates_jurisdiction_filename(tmp_path, seeded):
    first = runner(tmp_path, seeded)
    first.acquire()
    first.restore("legislature")
    name = "jurisdiction_ocd-jurisdiction-country:us-state:wi-government.json"
    (first.root / "_data/wi" / name).write_text('{"name": "Wisconsin"}', encoding="utf-8")
    complete(first, "legislature")

    finance = runner(tmp_path, seeded, "finance")
    assert finance.restore("finance")
    assert json.loads((finance.root / "_data/wi" / name).read_text()) == {"name": "Wisconsin"}


def test_finance_restore_preserves_historical_roster_attribution(tmp_path, seeded):
    from importer.import_openstates import build_rosters
    from importer.roster import Person, Term, load_legacy_terms

    source = tmp_path / "seed/pipeline"
    (source / "_data/legacy/wi_legislators.csv").write_text(
        "leg_id,full_name,last_name,party\nTEST001,Ann Able,Able,Test\n", encoding="utf-8")
    (source / "_data/legacy/wi_legislator_roles.csv").write_text(
        "leg_id,type,chamber,term,district,party\nTEST001,member,lower,2011-2012,5,Test\n",
        encoding="utf-8")
    (source / "_data/rosters/2013.json").write_text(json.dumps([
        {"name": "Bo Baker", "chamber": "lower", "district": 9},
    ]), encoding="utf-8")
    store = Store()
    seed(store, source, tmp_path / "historical-seed", REV)
    legislature = runner(tmp_path, store)
    legislature.acquire()
    legislature.restore("legislature")
    complete(legislature, "legislature")
    finance = runner(tmp_path, store, "finance")
    finance.restore("finance")

    people = load_legacy_terms(finance.root / "_data/legacy", [
        Person("p2", "Bo Baker", "Baker", "Test", None,
               terms=[Term("lower", 9, "2025-01-06", None)]),
    ])
    session_defs = {
        "2011": {"start_date": "2011-01-03", "end_date": "2013-01-01"},
        "2013": {"start_date": "2013-01-07", "end_date": "2015-01-01"},
    }
    rosters, _ = build_rosters(people, session_defs, set(session_defs),
                               finance.root / "_data/rosters")
    assert rosters["2011"].resolve("Ann Able", "lower").id == "legacy/TEST001"
    assert rosters["2013"].resolve("Bo Baker", "lower").from_listing


def test_failed_stage_never_advances_manifest(tmp_path, seeded):
    original = seeded.objects[LATEST]
    r = runner(tmp_path, seeded)
    r.acquire()
    r.restore("legislature")
    with pytest.raises(FileNotFoundError):
        r.checkpoint("legislature")
    assert seeded.objects[LATEST] == original
    assert not any(name.startswith("snapshots/") for name in seeded.objects)


def test_late_failure_publication_retry_is_idempotent_and_counts_preserved(tmp_path, seeded):
    original = seeded.objects[LATEST]
    r = complete_all(tmp_path, seeded)
    assert json.loads((r.root.parent / "data/.bill_counts.json").read_text()) == {"2025": 100}
    seeded.fail_latest = True
    with pytest.raises(StorageError):
        r.publish()
    assert seeded.objects[LATEST] == original
    assert len([n for n in seeded.objects if n.startswith("snapshots/")]) == 1
    seeded.fail_latest = False
    r.publish()
    published = seeded.objects[LATEST]
    r.publish()
    assert seeded.objects[LATEST] == published
    assert "database" not in seeded.read_json(LATEST)[0]["bundles"]


def test_stale_resume_rejected_after_newer_publication(tmp_path, seeded):
    r = runner(tmp_path, seeded)
    r.acquire()
    r.restore("legislature")
    complete(r, "legislature")
    latest, generation = seeded.read_json(LATEST)
    latest["run_id"] = "456"
    seeded.put_json(LATEST, latest, r.scratch, generation)
    with pytest.raises(Conflict, match="newer successful"):
        r.restore("legislature")


def test_corrupt_bundle_and_download_budget_fail_before_execution(tmp_path, seeded, monkeypatch):
    r = runner(tmp_path, seeded)
    r.acquire()
    monkeypatch.setattr("nightly.runner.MAX_DOWNLOAD", 1)
    with pytest.raises(ValueError, match="downloads exceed"):
        r.restore("legislature")
    monkeypatch.setattr("nightly.runner.MAX_DOWNLOAD", 1024**3)
    doc, generation = seeded.read_json(LATEST)
    doc["bundles"]["wi"]["sha256"] = "0" * 64
    seeded.put_json(LATEST, doc, r.scratch, generation)
    with pytest.raises(StorageError):
        r.restore("legislature")


def test_missing_bill_count_baseline_rejected(tmp_path, seeded):
    r = runner(tmp_path, seeded)
    r.acquire()
    doc, generation = seeded.read_json(LATEST)
    del doc["bill_counts"]
    seeded.put_json(LATEST, doc, r.scratch, generation)
    with pytest.raises(ValueError, match="bill-count baseline"):
        r.restore("legislature")


def test_expired_checkpoint_never_falls_back_to_seed(tmp_path, seeded):
    r = runner(tmp_path, seeded)
    r.acquire()
    r.restore("legislature")
    complete(r, "legislature")
    completed, _ = seeded.read_json(r.run_prefix + "legislature.json")
    expired = completed["bundles"]["wi"]["object"]
    del seeded.objects[expired]
    next_stage = runner(tmp_path, seeded, "finance")
    with pytest.raises(FileNotFoundError):
        next_stage.restore("finance")


def test_laptop_runs_respect_remote_lock(tmp_path, seeded, monkeypatch):
    from nightly import local_lock
    script = tmp_path / "repo/pipeline/nightly/local_lock.py"
    monkeypatch.setattr(local_lock, "__file__", str(script))
    r = runner(tmp_path, seeded)
    r.acquire()
    monkeypatch.setattr(local_lock, "GCS", lambda bucket: seeded)
    monkeypatch.setattr("sys.argv", ["lock", "acquire", "--owner", "local-" + "a" * 32,
                                     "--bucket", "test"])
    with pytest.raises(SystemExit, match="Another parser"):
        local_lock.main()
    monkeypatch.setattr("sys.argv", ["lock", "release", "--owner", "local-" + "a" * 32,
                                     "--bucket", "test"])
    with pytest.raises(SystemExit, match="refusing to release"):
        local_lock.main()
    assert seeded.read_json(LOCK)[0]["execution"] == r.execution


def test_sqlite_backup_includes_wal_commits(tmp_path, seeded):
    r = runner(tmp_path, seeded, "import")
    r.acquire()
    doc, generation = seeded.read_json(LATEST)
    doc.update(run_id="123", revision=REV, base_generation=generation, stage="import")
    r.context.write_text(json.dumps(doc))
    (r.root / "_data/wec").mkdir(parents=True)
    (r.root.parent / "data").mkdir()
    with sqlite3.connect(r.root.parent / "data/wi.sqlite") as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE probe(value)")
        db.execute("INSERT INTO probe VALUES (42)")
        db.commit()
        complete(r, "import")
        with sqlite3.connect(r.scratch / "database/wi.sqlite") as backup:
            assert backup.execute("SELECT value FROM probe WHERE value=42").fetchone() == (42,)


@pytest.mark.parametrize("member_name,kind", [
    ("../escape", tarfile.REGTYPE), ("wi/../../escape", tarfile.REGTYPE),
    ("/absolute", tarfile.REGTYPE), ("wi/link", tarfile.SYMTYPE),
    ("wi/hardlink", tarfile.LNKTYPE), ("other/file", tarfile.REGTYPE),
    ("wi/C:stream", tarfile.REGTYPE),
    ("wi/nested/C:/escape", tarfile.REGTYPE), ("wi/nested/C:escape", tarfile.REGTYPE),
])
def test_archive_rejects_unsafe_members(tmp_path, member_name, kind):
    archive = tmp_path / "input.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo(member_name)
        member.type = kind
        member.size = 1 if kind == tarfile.REGTYPE else 0
        member.linkname = "../../escape"
        bundle.addfile(member, io.BytesIO(b"x") if member.size else None)
    with pytest.raises(ValueError):
        unpack(archive, "wi", tmp_path / "restore", 100)


@pytest.mark.parametrize("filename", [
    "jurisdiction_ocd-jurisdiction-country:us-state:wi-government.json",
    "record.json:stream",
])
def test_archive_rejects_colon_names_on_windows(tmp_path, monkeypatch, filename):
    archive = tmp_path / "input.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo(f"wi/{filename}")
        member.size = 1
        bundle.addfile(member, io.BytesIO(b"x"))
    # Replace this module's os binding without changing pathlib's host platform.
    monkeypatch.setattr("nightly.archive.os", SimpleNamespace(name="nt"))
    with pytest.raises(ValueError, match="Unsafe"):
        unpack(archive, "wi", tmp_path / "restore", 1)
    assert not list((tmp_path / "restore/wi").iterdir())


def test_archive_roundtrip_and_existing_data_protected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "one").write_text("data")
    target = tmp_path / "bundle.tar.gz"
    size = pack(source, "wi", target)
    unpack(target, "wi", tmp_path / "restore", size)
    assert (tmp_path / "restore/wi/one").read_text() == "data"
    with pytest.raises(ValueError, match="empty destination"):
        unpack(target, "wi", tmp_path / "restore", size)


def test_failed_subprocess_cannot_leave_success_receipt(tmp_path, seeded, monkeypatch):
    r = runner(tmp_path, seeded)
    r.acquire()
    r.restore("legislature")
    import subprocess
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["python", "-m", "scraper.scrape"])
    monkeypatch.setattr("nightly.__main__.subprocess.run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        run_stage(r, "legislature", "2026")
    assert not (r.scratch / "success.json").exists()


def test_upstream_export_uses_hashes_and_platform_markers():
    path = Path(__file__).resolve().parents[1] / "vendor/openstates-scrapers/poetry.lock"
    if not path.exists():
        pytest.skip("Scraper submodule not initialized in this checkout")
    text = export(path)
    assert "openstates==6.25.5" in text
    assert "--hash=sha256:" in text
    assert "\n+" not in text
    assert 'sys_platform == "darwin"' in text


def test_workflow_sequence_and_private_data_guards():
    directory = Path(__file__).resolve().parents[2] / ".github/workflows"
    workflows = {p.name: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
                 for p in directory.glob("*.yml")}
    for name, workflow in workflows.items():
        assert not validate(workflow, name)
    concurrent = copy.deepcopy(workflows["nightly-parser.yml"])
    concurrent["jobs"]["finance"]["needs"] = "validate"
    assert validate(concurrent, "nightly-parser.yml")
    exposed = copy.deepcopy(workflows["parser-stage.yml"])
    exposed["jobs"]["stage"]["steps"].append({"uses": "actions/upload-artifact@" + REV})
    assert validate(exposed, "parser-stage.yml")


def test_cloud_cli_resolution_and_http_errors_do_not_expose_tokens(monkeypatch):
    import requests

    monkeypatch.setattr("nightly.storage.shutil.which", lambda name: "/tools/" + name)
    monkeypatch.setattr("nightly.storage.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(stdout="private-token\n"))
    store = GCS("test-bucket")
    assert store.http.headers["Authorization"] == "Bearer private-token"

    def interrupted(*args, **kwargs):
        raise requests.ConnectionError("private-token / signed-upload-session")

    monkeypatch.setattr(store.http, "request", interrupted)
    with pytest.raises(StorageError) as error:
        store.metadata("parser-state/latest.json")
    assert "private-token" not in str(error.value)
    assert "signed-upload-session" not in str(error.value)


def test_month_resume_and_failure_preserve_full_archive(tmp_path, seeded, monkeypatch):
    import subprocess

    original = copy.deepcopy(seeded.objects[LATEST])
    prep = prepare_finance(tmp_path, seeded)
    plan = prep.finance_plan()
    first = month_runner(tmp_path, seeded, "2025-01")
    assert first.restore("finance-month")
    complete_month(first)
    checkpoint = copy.deepcopy(seeded.objects[first.run_prefix + "months/2025-01.json"])
    broken = month_runner(tmp_path, seeded, "2025-02")
    broken.restore("finance-month")

    def interrupted(command, **kwargs):
        assert command[1:3] == ["-u", "-m"]
        assert command[3:] == ["scraper.fetch_cf_committees", "--since", "2025-02",
                               "--until", "2025-02"]
        (broken.root / "_data/cfis/pac-2025-02.json").write_text("[partial")
        raise subprocess.TimeoutExpired(command, 300)

    monkeypatch.setattr("nightly.__main__.subprocess.run", interrupted)
    with pytest.raises(subprocess.TimeoutExpired):
        run_stage(broken, "finance-month", "2026")
    with pytest.raises(FileNotFoundError):
        broken.checkpoint("finance-month")
    assert seeded.objects[LATEST] == original
    assert seeded.objects[first.run_prefix + "months/2025-01.json"] == checkpoint
    broken.release()

    retry_first = month_runner(tmp_path, seeded, "2025-01", "123-2")
    retry_first.acquire()
    assert retry_first.restore("finance-month") is False
    assert not (retry_first.root / "_data").exists()
    # Even after the calendar rolls forward, the original plan is authoritative.
    monkeypatch.setattr("nightly.runner.datetime", SimpleNamespace(now=lambda *_: None))
    for month in ("2025-03", "2025-02"):
        retry = month_runner(tmp_path, seeded, month, "123-2")
        assert retry.restore("finance-month")
        complete_month(retry)
    merged = runner(tmp_path, seeded, "finance-committees", execution="123-2")
    assert merged.restore("finance-committees")
    complete(merged, "finance-committees")
    doc = merged.load(merged.run_prefix + "finance-committees.json")
    assert doc["finance_completed_months"] == months_for(plan)
    assert doc["finance_as_of"] == "2025-03-31"
    assert seeded.objects[LATEST] == original


def test_merge_requires_every_month_and_counts_transfers(tmp_path, seeded, monkeypatch):
    prep = prepare_finance(tmp_path, seeded)
    plan = prep.finance_plan()
    for month in months_for(plan)[:-1]:
        r = month_runner(tmp_path, seeded, month)
        r.restore("finance-month")
        complete_month(r)
    merged = runner(tmp_path, seeded, "finance-committees")
    with pytest.raises(FileNotFoundError):
        merged.restore("finance-committees")
    assert not merged.context.exists()
    assert not (merged.root / "_data").exists()
    r = month_runner(tmp_path, seeded, months_for(plan)[-1])
    r.restore("finance-month")
    complete_month(r)
    transfer = plan["bundles"]["cfis"]["bytes"] + sum(
        prep.load_finance_month(plan, month)["bytes"] for month in months_for(plan))
    monkeypatch.setattr("nightly.runner.MAX_DOWNLOAD", plan["downloaded_bytes"] + transfer - 1)
    with pytest.raises(ValueError, match="downloads exceed"):
        merged.restore("finance-committees")
    monkeypatch.setattr("nightly.runner.MAX_DOWNLOAD", plan["downloaded_bytes"] + transfer)
    assert merged.restore("finance-committees")
    assert json.loads(merged.context.read_text())["downloaded_bytes"] == (
        plan["downloaded_bytes"] + transfer)


@pytest.mark.parametrize("field,value", [
    ("run_id", "456"), ("revision", "b" * 40), ("base_generation", "999"),
    ("month", "2025-02"), ("finance_as_of", "2025-04-01"),
])
def test_month_receipts_cannot_cross_runs_or_plans(tmp_path, seeded, field, value):
    prep = prepare_finance(tmp_path, seeded)
    r = month_runner(tmp_path, seeded, "2025-01")
    r.restore("finance-month")
    complete_month(r)
    name = r.run_prefix + "months/2025-01.json"
    doc, generation = seeded.read_json(name)
    doc[field] = value
    seeded.put_json(name, doc, r.scratch, generation)
    with pytest.raises(ValueError):
        prep.load_finance_month(prep.finance_plan(), "2025-01")


def test_new_run_does_not_inherit_finance_completion(tmp_path, seeded):
    last = complete_all(tmp_path, seeded)
    last.publish()
    last.release()
    next_run = runner(tmp_path, seeded, run_id="456", execution="456-1")
    next_run.acquire()
    assert next_run.restore("legislature")
    doc = json.loads(next_run.context.read_text())
    assert "completed_at" not in doc
    assert "snapshot" not in doc
    assert "finance_completed_months" not in doc


def test_month_rerun_after_publication_skips_expired_month_outputs(tmp_path, seeded):
    last = complete_all(tmp_path, seeded)
    last.publish()
    for name in list(seeded.objects):
        if "/months/" in name or name.endswith("finance-audit.json"):
            del seeded.objects[name]
    last.release()
    retry = month_runner(tmp_path, seeded, "2025-01", "123-2")
    retry.acquire()
    assert retry.restore("finance-month") is False
    assert months_for(retry.finance_plan()) == ["2025-01", "2025-02", "2025-03"]


def test_import_rejects_missing_finance_completion(tmp_path, seeded):
    last = complete_all(tmp_path, seeded)
    name = last.run_prefix + "federal.json"
    doc, generation = seeded.read_json(name)
    del doc["finance_completed_months"]
    seeded.put_json(name, doc, last.scratch, generation)
    del seeded.objects[last.run_prefix + "import.json"]
    r = runner(tmp_path, seeded, "import", execution="123-2")
    last.release()
    r.acquire()
    with pytest.raises(ValueError, match="partial import"):
        r.restore("import")


@pytest.mark.parametrize("mutation", ["parallel", "partial_matrix", "early_cleanup", "skip_merge"])
def test_month_workflow_guards(mutation):
    path = Path(__file__).resolve().parents[2] / ".github/workflows/nightly-parser.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    if mutation == "parallel":
        workflow["jobs"]["finance-months"]["strategy"]["max-parallel"] = 2
    elif mutation == "partial_matrix":
        workflow["jobs"]["finance-months"]["strategy"]["matrix"]["month"] = ["2025-01"]
    elif mutation == "early_cleanup":
        workflow["jobs"]["finish"]["needs"].remove("finance-months")
    else:
        workflow["jobs"]["community"]["needs"] = "finance-audit"
    assert validate(workflow, "nightly-parser.yml")
