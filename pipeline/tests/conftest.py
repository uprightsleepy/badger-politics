"""Shared scaffolding: one schema location, one way to build a schema-loaded DB."""

import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "importer" / "schema.sql"


@pytest.fixture()
def make_db():
    """Factory: connect to a path (or ':memory:') with the full schema applied."""

    def _make(path: Path | str) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        return conn

    return _make
