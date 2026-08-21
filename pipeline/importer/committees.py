"""Authoritative committee list from openstates/people YAML.

Committees are keyed by (chamber, normalized name) so referral texts
("Referred to Committee on Children and Families", chamber known from the
action) and hearing hosts ("Assembly Children and Families") resolve to the
same row. A chair is the first member whose role is chair/co-chair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CHAMBER_MAP = {"upper": "upper", "lower": "lower", "legislature": None}


@dataclass
class Committee:
    id: str  # ocd-organization id
    name: str
    chamber: str | None  # None = joint/legislature-wide
    chair_person_id: str | None
    chair_name: str | None
    members: list[dict] = field(default_factory=list)  # {name, role, person_id}


def normalize_name(name: str) -> str:
    """Case/punctuation-insensitive, with the noise prefixes 'joint' and
    'committee on' stripped (repeatedly — the committee-schedule feed can
    double them: 'Joint Joint Legislative Audit Committee'). Chamber-scoped
    keys keep same-stem committees in different chambers apart."""
    key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    while True:
        stripped = re.sub(r"^(joint |committee on )", "", key)
        if stripped == key:
            return key
        key = stripped


def load_committees(committees_dir: Path) -> list[Committee]:
    committees = []
    for path in sorted(committees_dir.glob("*.yml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw.get("classification") != "committee":
            continue
        chair = next(
            (m for m in raw.get("members", []) if m.get("role") in ("chair", "co-chair")),
            None,
        )
        committees.append(
            Committee(
                id=raw["id"],
                name=raw["name"],
                chamber=CHAMBER_MAP.get(raw.get("chamber"), None),
                chair_person_id=chair.get("person_id") if chair else None,
                chair_name=chair.get("name") if chair else None,
                members=[
                    {"name": m["name"], "role": m.get("role") or "member",
                     "person_id": m.get("person_id")}
                    for m in raw.get("members", [])
                    if m.get("person_id")
                ],
            )
        )
    return committees


class CommitteeIndex:
    def __init__(self, committees: list[Committee]):
        self.committees = committees
        self._by_key: dict[tuple[str | None, str], Committee] = {}
        for c in committees:
            self._by_key[(c.chamber, normalize_name(c.name))] = c

    def find(self, name: str, chamber: str | None) -> Committee | None:
        """Chamber-scoped lookup; joint committees match regardless of the
        chamber the referral happened in. Referral texts sometimes embed the
        chamber in the name ('Senate Organization') — strip and retry."""
        key = normalize_name(name)
        candidates = [(chamber, key), (None, key)]
        if key.startswith("senate "):
            candidates.append(("upper", key[len("senate "):]))
        elif key.startswith("assembly "):
            candidates.append(("lower", key[len("assembly "):]))
        for candidate in candidates:
            if candidate in self._by_key:
                return self._by_key[candidate]
        return None
