"""Session-scoped legislator rosters for vote/sponsor name attribution.

Loaded from openstates/people YAML — sitting members (data/wi/legislature)
plus, for historical sessions, retired members (data/wi/retired). Every
person carries their full term history; a Roster is built for a session's
date window, so names resolve against who actually served THEN, chamber-
scoped. Hard rule: an ambiguous name is a build failure, never a best guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class UnmatchedNameError(Exception):
    """A name on a vote/sponsor line resolved to no roster member."""


class AmbiguousNameError(Exception):
    """A name on a vote/sponsor line resolved to more than one roster member."""


@dataclass
class Term:
    chamber: str  # 'lower' | 'upper'
    district: int | None
    start: str  # ISO date
    end: str | None  # None = sitting


@dataclass
class Person:
    id: str
    name: str
    family_name: str
    party: str | None
    image_url: str | None
    aliases: list[str] = field(default_factory=list)
    terms: list[Term] = field(default_factory=list)


@dataclass
class Member:
    """One person serving in one chamber during one session window."""

    id: str
    name: str
    family_name: str
    party: str | None
    chamber: str
    district: int | None
    image_url: str | None
    aliases: list[str] = field(default_factory=list)


def _normalize(name: str) -> str:
    """Case/punctuation/whitespace-insensitive key for name comparison."""
    return re.sub(r"[^a-z]", "", name.lower())


def load_people(people_dirs: list[Path]) -> list[Person]:
    people = []
    for people_dir in people_dirs:
        for path in sorted(people_dir.glob("*.yml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            terms = [
                Term(
                    chamber=role["type"],
                    district=(
                        int(role["district"])
                        if str(role.get("district", "")).isdigit()
                        else None
                    ),
                    start=str(role.get("start_date") or "1900-01-01"),
                    end=str(role["end_date"]) if role.get("end_date") else None,
                )
                for role in raw.get("roles", [])
                if role.get("type") in ("lower", "upper")
            ]
            if not terms:
                continue
            parties = raw.get("party") or []
            people.append(
                Person(
                    id=raw["id"],
                    name=raw["name"],
                    family_name=raw.get("family_name") or raw["name"].split()[-1],
                    party=parties[-1]["name"] if parties else None,
                    image_url=raw.get("image"),
                    aliases=[n["name"] for n in raw.get("other_names", []) if n.get("name")],
                    terms=terms,
                )
            )
    return people


def roster_for(people: list[Person], start: str, end: str) -> Roster:
    """Roster of everyone with a term overlapping (start, end) — STRICT
    boundaries: WI terms end on the successor's inauguration day, which is
    also the new session's start date, so a term ending exactly on `start`
    served zero days of the session."""
    members: dict[tuple[str, str], Member] = {}  # (person, chamber) -> latest term
    for person in people:
        for term in person.terms:
            if term.start >= end or (term.end is not None and term.end <= start):
                continue
            key = (person.id, term.chamber)
            existing = members.get(key)
            if existing is None or term.start > existing._term_start:  # type: ignore[attr-defined]
                member = Member(
                    id=person.id,
                    name=person.name,
                    family_name=person.family_name,
                    party=person.party,
                    chamber=term.chamber,
                    district=term.district,
                    image_url=person.image_url,
                    aliases=person.aliases,
                )
                member._term_start = term.start  # type: ignore[attr-defined]
                members[key] = member
    return Roster(list(members.values()))


class Roster:
    """Chamber-scoped name resolution over one session's membership."""

    def __init__(self, members: list[Member]):
        self.members = members
        # (chamber, normalized-name-form) -> [Member]; every form a vote page
        # might print maps to the members it could mean.
        self._index: dict[tuple[str, str], list[Member]] = {}
        for m in members:
            forms = {m.name, m.family_name, *m.aliases}
            # 'Surname, F.' style used on WI roll call pages
            first = m.name.split()[0]
            forms.add(f"{m.family_name}, {first[0]}.")
            forms.add(f"{m.family_name}, {first}")
            for form in forms:
                key = (m.chamber, _normalize(form))
                bucket = self._index.setdefault(key, [])
                if m not in bucket:
                    bucket.append(m)

    def resolve(self, name: str, chamber: str) -> Member:
        """Resolve a printed name within one chamber, or fail loudly."""
        candidates = self._index.get((chamber, _normalize(name)), [])
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise UnmatchedNameError(f"{name!r} ({chamber}) matches no roster member")
        detail = ", ".join(f"{m.name} (district {m.district})" for m in candidates)
        raise AmbiguousNameError(f"{name!r} ({chamber}) is ambiguous: {detail}")

    def resolve_or_none(self, name: str, chamber: str) -> Member | None:
        """Lenient variant for sponsorships: unknown/ambiguous -> None, never a guess."""
        try:
            return self.resolve(name, chamber)
        except (UnmatchedNameError, AmbiguousNameError):
            return None
