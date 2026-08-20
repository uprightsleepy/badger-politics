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
    legacy_ids: list[str] = field(default_factory=list)


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


MERGES_PATH = Path(__file__).resolve().parent / "person_merges.json"
ALIASES_PATH = Path(__file__).resolve().parent / "person_aliases.json"
TERMS_PATH = Path(__file__).resolve().parent / "person_terms.json"


def apply_merges(people: list[Person]) -> list[Person]:
    """Fold manually-verified duplicate records into their canonical person
    (see person_merges.json). Terms and aliases merge; the dupe's name
    becomes an alias so listings naming either form still resolve."""
    import json

    merges = {
        k: v
        for k, v in json.loads(MERGES_PATH.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }
    by_id = {p.id: p for p in people}
    for dupe_id, canonical_id in merges.items():
        dupe, canonical = by_id.get(dupe_id), by_id.get(canonical_id)
        if dupe is None or canonical is None:
            continue
        canonical.terms.extend(dupe.terms)
        canonical.aliases.extend([dupe.name, *dupe.aliases])
        canonical.legacy_ids.extend(dupe.legacy_ids)
        del by_id[dupe_id]
    extra_aliases = {
        k: v
        for k, v in json.loads(ALIASES_PATH.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }
    for person_id, aliases in extra_aliases.items():
        if person_id in by_id:
            by_id[person_id].aliases.extend(aliases)
    extra_terms = {
        k: v
        for k, v in json.loads(TERMS_PATH.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }
    for person_id, terms in extra_terms.items():
        if person_id in by_id:
            by_id[person_id].terms.extend(
                Term(t["chamber"], t.get("district"), t["start"], t.get("end"))
                for t in terms
            )
    return list(by_id.values())


def load_people(people_dirs: list[Path]) -> list[Person]:
    people = []
    for people_dir in people_dirs:
        for path in sorted(people_dir.glob("*.yml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            terms = []
            for role in raw.get("roles", []):
                if role.get("type") not in ("lower", "upper"):
                    continue
                start = str(role["start_date"]) if role.get("start_date") else None
                end = str(role["end_date"]) if role.get("end_date") else None
                if not start and end:
                    # some files omit start_date (e.g. executives' past
                    # legislative roles); assume one constitutional term —
                    # under-coverage fails loudly as unmatched, never as a
                    # wrong attribution
                    term_years = 2 if role["type"] == "lower" else 4
                    start = f"{int(end[:4]) - term_years}{end[4:]}"
                if not start:
                    continue  # undatable role: exclude rather than guess
                terms.append(
                    Term(
                        chamber=role["type"],
                        district=(
                            int(role["district"])
                            if str(role.get("district", "")).isdigit()
                            else None
                        ),
                        start=start,
                        end=end,
                    )
                )
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
                    legacy_ids=[
                        i["identifier"]
                        for i in raw.get("other_identifiers", [])
                        if i.get("scheme") == "legacy_openstates" and i.get("identifier")
                    ],
                )
            )
    return apply_merges(people)


def load_legacy_terms(legacy_dir: Path, people: list[Person]) -> list[Person]:
    """Fold the openstates legacy CSV dump (data.openstates.org, 2009-2018
    era) into the people list: per-biennium member terms attach to known
    people via their legacy_openstates identifier, and members with no
    modern people-file at all are synthesized. This is the authoritative
    membership source for sessions older than docs.legis's listings (2013+)."""
    import csv

    roles_path = legacy_dir / "wi_legislator_roles.csv"
    legs_path = legacy_dir / "wi_legislators.csv"
    if not roles_path.exists():
        return people

    by_legacy: dict[str, Person] = {}
    for person in people:
        # merged duplicates may carry several legacy ids
        for legacy_id in person.legacy_ids:
            by_legacy[legacy_id] = person
    legacy_meta = {
        row["leg_id"]: row
        for row in csv.DictReader(legs_path.open(encoding="utf-8"))
    }

    synthesized: dict[str, Person] = {}
    for row in csv.DictReader(roles_path.open(encoding="utf-8")):
        if row["type"] != "member" or row["chamber"] not in ("lower", "upper"):
            continue
        term_years = row["term"].split("-")
        if len(term_years) != 2 or not term_years[0].isdigit():
            continue
        year = int(term_years[0])
        term = Term(
            chamber=row["chamber"],
            district=int(row["district"]) if row["district"].isdigit() else None,
            start=f"{year}-01-05",
            end=f"{year + 2}-01-03",
        )
        person = by_legacy.get(row["leg_id"]) or synthesized.get(row["leg_id"])
        if person is None:
            meta = legacy_meta.get(row["leg_id"], {})
            name = meta.get("full_name") or row["leg_id"]
            person = Person(
                id=f"legacy/{row['leg_id']}",
                name=name,
                family_name=meta.get("last_name") or name.split()[-1],
                party=row.get("party") or meta.get("party") or None,
                image_url=meta.get("photo_url") or None,
                legacy_ids=[row["leg_id"]],
            )
            synthesized[row["leg_id"]] = person
        # skip if an equivalent term is already covered
        covered = any(
            t.chamber == term.chamber and t.start <= term.start and
            (t.end is None or t.end >= term.end)
            for t in person.terms
        )
        if not covered:
            person.terms.append(term)
    return people + list(synthesized.values())


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


def find_person(people: list[Person], name: str) -> Person:
    """Resolve a full name (from an authoritative membership listing) to a
    Person. Exact normalized match on name/aliases first; else unique
    family-name + first-name-prefix match. Ambiguity or absence raises —
    membership identity is never guessed."""
    key = _normalize(name)
    exact = [
        p for p in people
        if _normalize(p.name) == key or any(_normalize(a) == key for a in p.aliases)
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise AmbiguousNameError(f"listing name {name!r} matches multiple people")
    words = name.replace(",", " ").split()
    family, first = _normalize(words[-1]), _normalize(words[0])
    loose = [
        p for p in people
        if _normalize(p.family_name) == family
        and (
            _normalize(p.name.split()[0]).startswith(first)
            or first.startswith(_normalize(p.name.split()[0]))
        )
    ]
    if len(loose) == 1:
        return loose[0]
    if len(loose) > 1:
        raise AmbiguousNameError(f"listing name {name!r} is ambiguous across people files")
    # nicknames ('Vincent' vs 'Vinnie') defeat prefix matching: accept a
    # family-only match when exactly one person bears that surname
    family_only = [p for p in people if _normalize(p.family_name) == family]
    if len(family_only) == 1:
        return family_only[0]
    if not family_only:
        raise UnmatchedNameError(f"listing name {name!r} matches no known person")
    raise AmbiguousNameError(f"listing name {name!r} is ambiguous across people files")


def merge_listing(roster: Roster, listing: list[dict], people: list[Person]) -> Roster:
    """Union a docs.legis membership listing into a windowed roster: the
    listing is authoritative for who served (it includes mid-session
    replacements and members whose people-file dates are incomplete)."""
    members = {(m.id, m.chamber): m for m in roster.members}
    for entry in listing:
        person = find_person(people, entry["name"])
        key = (person.id, entry["chamber"])
        if key not in members:
            members[key] = Member(
                id=person.id,
                name=person.name,
                family_name=person.family_name,
                party=person.party,
                chamber=entry["chamber"],
                district=entry.get("district"),
                image_url=person.image_url,
                aliases=person.aliases,
            )
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
            words = m.name.split()
            first = words[0]
            forms.add(f"{m.family_name}, {first[0]}.")
            forms.add(f"{m.family_name}, {first}")
            if len(words) >= 3:
                # compound surnames print as the last two words
                # ('Nikiya Harris Dodd' appears as 'HARRIS DODD')
                compound = " ".join(words[-2:])
                forms.add(compound)
                forms.add(f"{compound}, {first[0]}.")
            for form in forms:
                key = (m.chamber, _normalize(form))
                bucket = self._index.setdefault(key, [])
                if m not in bucket:
                    bucket.append(m)

    # docs.legis roll-call tables truncate long surnames (e.g. Cabral-Guevara
    # prints as 'CABRAL-GUEVA'); a printed name at least this long (normalized)
    # may prefix-match a single longer roster form. Short names never do —
    # 'KRUG' must not drift into 'KRUGER'.
    TRUNCATION_MIN = 10

    def resolve(self, name: str, chamber: str) -> Member:
        """Resolve a printed name within one chamber, or fail loudly."""
        key = _normalize(name)
        candidates = self._index.get((chamber, key), [])
        if not candidates and len(key) >= self.TRUNCATION_MIN:
            prefix_hits = {
                m.id: m
                for (ch, form), members in self._index.items()
                if ch == chamber and form.startswith(key)
                for m in members
            }
            candidates = list(prefix_hits.values())
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
