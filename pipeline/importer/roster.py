"""Session-scoped legislator roster for vote/sponsor name attribution.

Loaded from openstates/people YAML (data/wi/legislature). Resolution is
chamber-scoped and alias-aware. Hard rule: an ambiguous name is a build
failure, never a best guess — misattributing a vote is the worst bug this
site can have.
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
class Member:
    id: str
    name: str
    family_name: str
    party: str | None
    chamber: str  # 'lower' | 'upper'
    district: int | None
    image_url: str | None
    aliases: list[str] = field(default_factory=list)


def _normalize(name: str) -> str:
    """Case/punctuation/whitespace-insensitive key for name comparison."""
    return re.sub(r"[^a-z]", "", name.lower())


def _current_role(person: dict) -> dict | None:
    """The role with no end_date (the sitting one), if any."""
    for role in person.get("roles", []):
        if role.get("type") in ("lower", "upper") and not role.get("end_date"):
            return role
    return None


def load_members(people_dir: Path) -> list[Member]:
    members = []
    for path in sorted(people_dir.glob("*.yml")):
        person = yaml.safe_load(path.read_text(encoding="utf-8"))
        role = _current_role(person)
        if role is None:
            continue
        district = role.get("district")
        parties = person.get("party") or []
        members.append(
            Member(
                id=person["id"],
                name=person["name"],
                family_name=person.get("family_name") or person["name"].split()[-1],
                party=parties[0]["name"] if parties else None,
                chamber=role["type"],
                district=int(district) if district and str(district).isdigit() else None,
                image_url=person.get("image"),
                aliases=[n["name"] for n in person.get("other_names", []) if n.get("name")],
            )
        )
    return members


class Roster:
    """Chamber-scoped name resolution over the sitting membership."""

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
            raise UnmatchedNameError(f"{name!r} ({chamber}) matches no sitting legislator")
        detail = ", ".join(f"{m.name} (district {m.district})" for m in candidates)
        raise AmbiguousNameError(f"{name!r} ({chamber}) is ambiguous: {detail}")

    def resolve_or_none(self, name: str, chamber: str) -> Member | None:
        """Lenient variant for sponsorships: unknown/ambiguous -> None, never a guess."""
        try:
            return self.resolve(name, chamber)
        except (UnmatchedNameError, AmbiguousNameError):
            return None


def load_roster(people_dir: Path) -> Roster:
    members = load_members(people_dir)
    if len(members) < 120:
        raise RuntimeError(
            f"roster has only {len(members)} sitting members (expected ~132); "
            "refresh with: python -m scraper.fetch_people"
        )
    return Roster(members)
