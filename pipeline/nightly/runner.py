"""Checkpoint protocol shared by the CLI and offline failure-path tests."""

from __future__ import annotations

import copy
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from nightly.archive import MAX_EXPANDED, pack, unpack
from nightly.finance import months_for, require_complete
from nightly.stages import READS, SOURCES, STAGES, WRITES
from nightly.storage import Conflict

PREFIX = "parser-state/"
LATEST = PREFIX + "latest.json"
LOCK = PREFIX + "lock.json"
MAX_STATE = 1024**3
MAX_DOWNLOAD = 50 * 1024**3 // 30


def source_path(root: Path, name: str) -> Path:
    if name == "scraper_cache":
        return root / "vendor/openstates-scrapers/_cache"
    return root / "_data" / name


def validate_bundle(name: str, ref: dict):
    obj = ref.get("object", "")
    if (not obj.startswith((PREFIX + "seed/", PREFIX + "checkpoints/"))
            or not re.fullmatch(r"[a-zA-Z0-9_./-]+", obj) or ".." in obj.split("/")
            or not re.fullmatch(r"[0-9]+", str(ref.get("generation", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", ref.get("sha256", ""))
            or not 0 < ref.get("bytes", 0) <= MAX_STATE
            or not 0 <= ref.get("expanded_bytes", -1) <= MAX_EXPANDED):
        raise ValueError(f"Invalid bundle descriptor: {name}")


def validate_manifest(doc: dict):
    if doc.get("version") != 1 or set(doc.get("bundles", {})) - {*SOURCES, "database"}:
        raise ValueError("Unknown checkpoint format or source bundle")
    if not set(SOURCES).issubset(doc["bundles"]):
        raise ValueError("Source manifest is incomplete; seed all source directories")
    counts = doc.get("bill_counts")
    if not isinstance(counts, dict) or not counts or any(
        not isinstance(value, int) or value < 0 for value in counts.values()
    ):
        raise ValueError("Missing bill-count baseline; never reset the historical integrity gate")
    for name, ref in doc["bundles"].items():
        validate_bundle(name, ref)
    if sum(ref["bytes"] for name, ref in doc["bundles"].items()
           if name != "database") > MAX_STATE:
        raise ValueError("Compressed source state exceeds 1 GiB budget")


class Runner:
    def __init__(self, store, root: Path, run_id: str, revision: str, execution: str):
        if not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Run ID and revision must be immutable GitHub identifiers")
        if not re.fullmatch(r"[0-9]+-[0-9]+", execution):
            raise ValueError("Invalid execution identifier")
        self.store, self.root = store, root
        self.run_id, self.revision, self.execution = run_id, revision, execution
        self.scratch = root.parent / ".private" / "nightly"
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.context = self.scratch / "context.json"
        self.run_prefix = f"{PREFIX}checkpoints/runs/{run_id}/"

    def acquire(self):
        try:
            self.store.put_json(LOCK, {"execution": self.execution}, self.scratch)
        except Conflict:
            self.check_lock()

    def check_lock(self):
        lock, _ = self.store.read_json(LOCK)
        if lock.get("execution") != self.execution:
            raise Conflict("Another execution owns the parser lock; recover it explicitly")

    def release(self):
        try:
            lock, generation = self.store.read_json(LOCK)
        except FileNotFoundError:
            return
        if lock.get("execution") == self.execution:
            self.store.delete(LOCK, generation)

    def load(self, name: str) -> dict:
        document, _ = self.store.read_json(name)
        validate_manifest(document)
        return document

    def same_run(self, doc: dict):
        if doc.get("run_id") != self.run_id or doc.get("revision") != self.revision:
            raise ValueError("Resume requires the original run ID and exact source revision")

    def current_base(self, doc: dict):
        latest, generation = self.store.read_json(LATEST)
        if latest.get("run_id") == self.run_id:
            self.same_run(latest)
            return True
        if generation != doc["base_generation"]:
            raise Conflict("A newer successful run exists; stale checkpoints cannot be resumed")
        return False

    def receipt(self, stage: str) -> dict:
        return {"stage": stage, "revision": self.revision, "execution": self.execution}

    def log_name(self, stage: str) -> str:
        return stage

    def finance_plan(self) -> dict:
        latest, _ = self.store.read_json(LATEST)
        if latest.get("run_id") == self.run_id:
            validate_manifest(latest)
            self.same_run(latest)
            require_complete(latest)
            return latest
        doc = self.load(self.run_prefix + "finance-audit.json")
        self.same_run(doc)
        self.current_base(doc)
        if doc.get("stage") != "finance-audit":
            raise ValueError("Finance preparation has not completed")
        months_for(doc)
        return doc

    def load_finance_month(self, doc: dict, month: str) -> dict:
        if month not in months_for(doc):
            raise ValueError("Unexpected finance month")
        receipt, _ = self.store.read_json(self.run_prefix + f"months/{month}.json")
        self.same_run(receipt)
        if (receipt.get("version") != 1 or receipt.get("stage") != "finance-month"
                or receipt.get("month") != month
                or receipt.get("base_generation") != doc["base_generation"]
                or receipt.get("finance_as_of") != doc["finance_as_of"]):
            raise ValueError("Monthly finance checkpoint does not match this run's plan")
        ref = receipt["bundle"]
        validate_bundle("cfis", ref)
        if not ref["object"].startswith(self.run_prefix + f"months/{month}-"):
            raise ValueError("Monthly finance bundle belongs to a different month/run")
        return ref

    def restore(self, stage: str) -> bool:
        self.check_lock()
        latest, generation = self.store.read_json(LATEST)
        validate_manifest(latest)
        if latest.get("run_id") == self.run_id:
            self.same_run(latest)
            return False  # Idempotent rerun after successful publication.
        try:
            cached = self.load(self.run_prefix + stage + ".json")
        except FileNotFoundError:
            cached = None
        if cached:
            self.same_run(cached)
            self.current_base(cached)
            if cached.get("stage") != stage:
                raise ValueError("Checkpoint stage mismatch")
            return False
        position = STAGES.index(stage)
        if position:
            doc = self.load(self.run_prefix + STAGES[position - 1] + ".json")
            self.same_run(doc)
            self.current_base(doc)
            if doc.get("stage") != STAGES[position - 1]:
                raise ValueError("Checkpoint stages must execute in order")
        else:
            doc = copy.deepcopy(latest)
            for key in ("snapshot", "completed_at", "finance_completed_months"):
                doc.pop(key, None)
            now = datetime.now(UTC)
            doc.update(run_id=self.run_id, revision=self.revision, base_generation=generation,
                       started_at=now.strftime("%Y-%m-%dT%H%M%S"),
                       finance_as_of=now.date().isoformat(),
                       downloaded_bytes=0)
            months_for(doc)
        if position > STAGES.index("finance-committees"):
            require_complete(doc)
        month_refs = {month: self.load_finance_month(doc, month) for month in months_for(doc)} \
            if stage == "finance-committees" else {}
        required = READS[stage]
        download = (sum(doc["bundles"][name]["bytes"] for name in required)
                    + sum(ref["bytes"] for ref in month_refs.values()))
        if doc["downloaded_bytes"] + download > MAX_DOWNLOAD:
            raise ValueError("Projected nightly downloads exceed 50 GiB/month; review shard sizing")
        self.root.joinpath("_data").mkdir(exist_ok=True)
        for name in required:
            ref = doc["bundles"][name]
            target = self.scratch / f"{name}.tar.gz"
            self.store.download(ref, target)
            unpack(target, name, self.root / "_data", ref["expanded_bytes"])
            target.unlink()
        for month, ref in month_refs.items():
            target = self.scratch / f"{month}.tar.gz"
            self.store.download(ref, target)
            unpack(target, "cfis", self.scratch / "finance-months" / month, ref["expanded_bytes"])
            target.unlink()
        if "scraper_cache" in required:
            cache = source_path(self.root, "scraper_cache")
            if cache.exists():
                raise ValueError("Refusing to replace an existing scraper cache")
            cache.parent.mkdir(parents=True, exist_ok=True)
            (self.root / "_data/scraper_cache").rename(cache)
        if "database" in required:
            self.root.parent.joinpath("data").mkdir(exist_ok=True)
            target = self.root.parent / "data/wi.sqlite"
            if target.exists():
                raise ValueError("Refusing to replace an existing working SQLite file")
            shutil.copyfile(self.root / "_data/database/wi.sqlite", target)
            (target.parent / ".bill_counts.json").write_text(
                json.dumps(doc["bill_counts"]), encoding="utf-8")
        doc["downloaded_bytes"] += download
        doc["stage"] = stage
        self.context.write_text(json.dumps(doc), encoding="utf-8")
        return True

    def checkpoint_context(self, stage: str) -> dict:
        self.check_lock()
        doc = json.loads(self.context.read_text(encoding="utf-8"))
        self.same_run(doc)
        self.current_base(doc)
        receipt = json.loads((self.scratch / "success.json").read_text(encoding="utf-8"))
        if receipt != self.receipt(stage):
            raise ValueError("Stage did not complete successfully in this execution")
        if doc["stage"] != stage:
            raise ValueError("Stage mismatch")
        return doc

    def checkpoint(self, stage: str):
        doc = self.checkpoint_context(stage)
        if stage == "finance-committees":
            marker = self.scratch / "finance-complete.json"
            merged = json.loads(marker.read_text(encoding="utf-8"))
            if merged != {"run_id": self.run_id, "revision": self.revision,
                          "months": months_for(doc)}:
                raise ValueError("Finance merge did not complete every planned month")
            doc["finance_completed_months"] = months_for(doc)
        for name in WRITES[stage]:
            source = source_path(self.root, name)
            if name == "database":
                source = self.scratch / "database"
                source.mkdir(exist_ok=True)
                # SQLite backup captures a consistent database, including WAL.
                database_uri = (self.root.parent / "data/wi.sqlite").resolve().as_uri() + "?mode=ro"
                with sqlite3.connect(database_uri, uri=True) as db:
                    with sqlite3.connect(source / "wi.sqlite") as backup:
                        db.backup(backup)
            target = self.scratch / f"{name}.tar.gz"
            expanded = pack(source, name, target)
            if target.stat().st_size > MAX_STATE:
                raise ValueError("Bundle exceeds 1 GiB budget")
            obj = self.run_prefix + f"{stage}-{self.execution}-{name}.tar.gz"
            doc["bundles"][name] = {**self.store.upload(obj, target), "expanded_bytes": expanded}
            target.unlink()
        validate_manifest(doc)
        if stage == "enrich":
            doc["bill_counts"] = json.loads(
                (self.root.parent / "data/.bill_counts.json").read_text(encoding="utf-8"))
            # The existing deployment workflow consumes sqlite.gz, not tar.
            import gzip
            snapshot = self.scratch / "wi.sqlite.gz"
            with (self.scratch / "database/wi.sqlite").open("rb") as src:
                with gzip.open(snapshot, "wb", compresslevel=6) as dst:
                    shutil.copyfileobj(src, dst)
            doc["snapshot"] = self.store.upload(
                self.run_prefix + f"validated-{self.execution}.sqlite.gz", snapshot)
            snapshot.unlink()
        self.store.put_json(self.run_prefix + stage + ".json", doc, self.scratch)

    def publish(self):
        self.check_lock()
        doc = self.load(self.run_prefix + "enrich.json")
        self.same_run(doc)
        if self.current_base(doc):
            return
        if doc.get("stage") != "enrich":
            raise ValueError("Final integrity stage is incomplete")
        require_complete(doc)
        ref = doc["snapshot"]
        if (not ref["object"].startswith(self.run_prefix)
                or not re.fullmatch(r"[0-9]+", ref["generation"])):
            raise ValueError("Invalid final snapshot")
        name = f"snapshots/wi-{doc['started_at']}-{self.run_id}.sqlite.gz"
        doc["snapshot"] = self.store.copy(ref, name)
        doc["completed_at"] = datetime.now(UTC).isoformat()
        doc["bundles"].pop("database")
        self.store.put_json(LATEST, doc, self.scratch, doc["base_generation"])


def seed(store, root: Path, scratch: Path, revision: str):
    """Operator-only bootstrap. Never replaces an existing current manifest."""
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Seed needs a source revision")
    try:
        store.metadata(LATEST)
    except FileNotFoundError:
        pass
    else:
        raise Conflict("Current state already exists; seed cannot replace it")
    counts = json.loads((root.parent / "data/.bill_counts.json").read_text(encoding="utf-8"))
    doc = {"version": 1, "revision": revision, "bundles": {}, "bill_counts": counts}
    scratch.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")
    # Pack and check the ENTIRE budget before creating any cloud objects.
    for name in SOURCES:
        target = scratch / f"{name}.tar.gz"
        expanded = pack(source_path(root, name), name, target)
        doc["bundles"][name] = {"bytes": target.stat().st_size, "expanded_bytes": expanded}
    if sum(ref["bytes"] for ref in doc["bundles"].values()) > MAX_STATE:
        raise ValueError("Source seed exceeds 1 GiB compressed; review storage budget")
    for name, ref in doc["bundles"].items():
        uploaded = store.upload(f"{PREFIX}seed/{stamp}-{revision}/{name}.tar.gz",
                                scratch / f"{name}.tar.gz")
        ref.update(uploaded)
    validate_manifest(doc)
    store.put_json(LATEST, doc, scratch)
    return doc
