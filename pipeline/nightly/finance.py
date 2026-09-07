"""Frozen finance coverage and a complete, chronological merge of monthly outputs."""

from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

from scraper.cfis_api import month_windows


def months_for(doc: dict) -> list[str]:
    as_of = date.fromisoformat(doc["finance_as_of"])
    months = [label for label, _, _ in month_windows("2025-01", as_of.strftime("%Y-%m"))]
    # Fail explicitly before exceeding GitHub's matrix limit; never truncate coverage.
    if not 1 <= len(months) <= 256:
        raise ValueError("Finance month plan exceeds the supported job count")
    return months


def require_complete(doc: dict):
    if doc.get("finance_completed_months") != months_for(doc):
        raise ValueError("Finance month coverage is incomplete; refusing a partial import")


def read_rows(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid finance archive structure")
    return rows


def read_registry(path: Path) -> dict[int, dict]:
    result = {}
    for row in read_rows(path):
        key = row.get("entity_id")
        if type(key) is not int or key <= 0 or key in result or not row.get("name"):
            raise ValueError("Invalid or duplicate committee registry entry")
        result[key] = row
    return result


def validate_transactions(path: Path, month: str, seen: set[int]):
    for row in read_rows(path):
        key = row.get("id")
        # A moved/amended transaction can appear in two independently fetched
        # windows. Stop for reconciliation instead of letting INSERT OR REPLACE hide it.
        if type(key) is not int or key <= 0 or key in seen:
            raise ValueError("Invalid or duplicate finance transaction ID")
        if not isinstance(row.get("date"), str) or row["date"][:7] != month:
            raise ValueError("Finance transaction falls outside its archive month")
        date.fromisoformat(row["date"])
        seen.add(key)


def validate_month(directory: Path, month: str):
    if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", month):
        raise ValueError("Invalid finance month")
    if {p.name for p in directory.iterdir()} != {f"pac-{month}.json", "committees.json"}:
        raise ValueError("Monthly output must contain exactly its transactions and registry")
    validate_transactions(directory / f"pac-{month}.json", month, set())
    read_registry(directory / "committees.json")


def merge_months(archive: Path, inputs: Path, months: list[str]):
    if not months or sorted(set(months)) != months:
        raise ValueError("Finance months must be unique and chronological")
    if {p.name for p in inputs.iterdir()} != set(months):
        raise ValueError("Missing or unexpected finance month input")
    registry = read_registry(archive / "committees.json")
    seen: set[int] = set()
    # Validate the entire resulting archive before replacing any source file.
    for path in sorted(archive.glob("pac-*.json")):
        month = path.stem.removeprefix("pac-")
        if month not in months:
            validate_transactions(path, month, seen)
    for month in months:
        directory = inputs / month / "cfis"
        validate_month(directory, month)
        validate_transactions(directory / f"pac-{month}.json", month, seen)
        # Match the unsplit collector: the latest chronological observation wins,
        # irrespective of the order in which matrix jobs finished.
        registry.update(read_registry(directory / "committees.json"))
    for month in months:
        target = archive / f"pac-{month}.json"
        pending = target.with_suffix(".pending")
        shutil.copyfile(inputs / month / "cfis" / target.name, pending)
        pending.replace(target)
    target = archive / "committees.json"
    pending = target.with_suffix(".pending")
    pending.write_text(json.dumps(sorted(registry.values(), key=lambda row: row["entity_id"]),
                                  indent=0), encoding="utf-8")
    pending.replace(target)


def main():
    root = Path(__file__).resolve().parents[1]
    scratch = root.parent / ".private/nightly"
    doc = json.loads((scratch / "context.json").read_text(encoding="utf-8"))
    if doc.get("stage") != "finance-committees":
        raise ValueError("Restore all finance months before merging")
    months = months_for(doc)
    merge_months(root / "_data/cfis", scratch / "finance-months", months)
    (scratch / "finance-complete.json").write_text(json.dumps({
        "run_id": doc["run_id"], "revision": doc["revision"], "months": months,
    }), encoding="utf-8")
    print(f"Merged all {len(months)} finance months; full archive preserved", flush=True)


if __name__ == "__main__":
    main()
