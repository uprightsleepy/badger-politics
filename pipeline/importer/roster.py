"""Session-scoped legislator rosters for vote and sponsor attribution.
Hard rule: an ambiguous name is a build failure, never a best guess."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# sorts after any real date: an endless term is still being served
# (checks.py inlines the same value in SQL — keep them in step)
OPEN_END = "9999"

MERGES_PATH = Path(__file__).resolve().parent / "person_merges.json"
ALIASES_PATH = Path(__file__).resolve().parent / "person_aliases.json"
TERMS_PATH = Path(__file__).resolve().parent / "person_terms.json"


class UnmatchedNameError(Exception):
    pass


class AmbiguousNameError(Exception):
    pass


@dataclass
class Term:
    chamber: str  # 'lower' | 'upper'
    district: int | None
    start: str
    end: str | None  # None = sitting
    # synthetic terms (startless-role guesses, legacy Jan-5 boundaries)
    # build rosters but are never persisted; session windows replace them
    synthetic: bool = False


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

    @classmethod
    def from_person(cls, person: Person, chamber: str, district: int | None) -> Member:
        return cls(
            id=person.id,
            name=person.name,
            family_name=person.family_name,
            party=person.party,
            chamber=chamber,
            district=district,
            image_url=person.image_url,
            aliases=person.aliases,
        )


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def _curation(path: Path) -> dict:
    """Load a curation JSON, dropping the _comment key."""
    return {
        k: v
        for k, v in json.loads(path.read_text(encoding="utf-8")).items()
        if not k.startswith("_")
    }


def apply_merges(people: list[Person]) -> list[Person]:
    """Fold manually verified duplicates, extra aliases, and missing terms
    (see the three curation JSON files) into the people list."""
    by_id = {p.id: p for p in people}
    for dupe_id, canonical_id in _curation(MERGES_PATH).items():
        dupe, canonical = by_id.get(dupe_id), by_id.get(canonical_id)
        if dupe is None or canonical is None:
            continue
        canonical.terms.extend(dupe.terms)
        canonical.aliases.extend([dupe.name, *dupe.aliases])
        canonical.legacy_ids.extend(dupe.legacy_ids)
        del by_id[dupe_id]
    for person_id, aliases in _curation(ALIASES_PATH).items():
        if person_id in by_id:
            by_id[person_id].aliases.extend(aliases)
    for person_id, terms in _curation(TERMS_PATH).items():
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
                synthetic = False
                if not start and end:
                    # startless role: assume one constitutional term; under-
                    # coverage fails loudly as unmatched, never misattributes
                    term_years = 2 if role["type"] == "lower" else 4
                    start = f"{int(end[:4]) - term_years}{end[4:]}"
                    synthetic = True
                if not start:
                    continue
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
                        synthetic=synthetic,
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
    """Fold the openstates legacy CSV dump (2009-2018 era) into the people
    list; members with no modern file are synthesized. Authoritative
    membership for sessions before docs.legis listings begin (2013)."""
    roles_path = legacy_dir / "wi_legislator_roles.csv"
    legs_path = legacy_dir / "wi_legislators.csv"
    if not roles_path.exists():
        return people

    by_legacy: dict[str, Person] = {}
    for person in people:
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
            synthetic=True,  # Jan-5 boundary is a guess; sessions convene Jan-3
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
                # legacy photo urls point at long-dead legis.wisconsin.gov
                # paths (verified 404 in the 2026-08 link audit); no photo
                # beats a broken one
                image_url=None,
                legacy_ids=[row["leg_id"]],
            )
            synthesized[row["leg_id"]] = person
        # any overlap defers to the modern file: it knows about recalls and
        # resignations the legacy CSV predates (Wanggaard's 2012 recall);
        # legacy rows only fill bienniums the modern file doesn't touch
        covered = any(
            t.chamber == term.chamber and t.start < term.end and
            term.start < (t.end or OPEN_END)
            for t in person.terms
        )
        if not covered:
            person.terms.append(term)
    return people + list(synthesized.values())


def roster_for(people: list[Person], start: str, end: str) -> Roster:
    """Members with a term overlapping (start, end), strict boundaries:
    WI terms end on inauguration day, which is the next session's start."""
    latest: dict[tuple[str, str], tuple[str, Member]] = {}  # key -> (term_start, member)
    for person in people:
        for term in person.terms:
            if term.start >= end or (term.end is not None and term.end <= start):
                continue
            key = (person.id, term.chamber)
            existing = latest.get(key)
            if existing is None or term.start > existing[0]:
                latest[key] = (term.start, Member.from_person(person, term.chamber, term.district))
    return Roster([m for _, m in latest.values()])


def find_person(people: list[Person], name: str) -> Person:
    """Resolve a listing name to a Person; ambiguity or absence raises."""
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
    # nicknames defeat prefix matching; accept a unique family-only match
    family_only = [p for p in people if _normalize(p.family_name) == family]
    if len(family_only) == 1:
        return family_only[0]
    if not family_only:
        raise UnmatchedNameError(f"listing name {name!r} matches no known person")
    raise AmbiguousNameError(f"listing name {name!r} is ambiguous across people files")


def merge_listing(roster: Roster, listing: list[dict], people: list[Person]) -> Roster:
    """Union a docs.legis membership listing (authoritative for who served,
    including mid-session replacements) into a windowed roster."""
    members = {(m.id, m.chamber): m for m in roster.members}
    for entry in listing:
        person = find_person(people, entry["name"])
        key = (person.id, entry["chamber"])
        if key not in members:
            members[key] = Member.from_person(person, entry["chamber"], entry.get("district"))
    return Roster(list(members.values()))


class Roster:
    """Chamber-scoped name resolution over one session's membership."""

    # printed names at least this long may prefix-match one longer roster
    # form (docs.legis truncates: 'CABRAL-GUEVA'); short names never do
    TRUNCATION_MIN = 10

    def __init__(self, members: list[Member]):
        self.members = members
        # the index never changes after init, so resolutions can't either;
        # only successes are cached (failures raise and abort the run)
        self._resolved: dict[tuple[str, str], Member] = {}
        self._index: dict[tuple[str, str], list[Member]] = {}
        for m in members:
            forms = {m.name, m.family_name, *m.aliases}
            words = m.name.split()
            first = words[0]
            forms.add(f"{m.family_name}, {first[0]}.")
            forms.add(f"{m.family_name}, {first}")
            # sponsor lines print initial-first ('C. Taylor') to split
            # same-surname members; two members sharing surname and initial
            # would collide into one bucket and stay ambiguous
            forms.add(f"{first[0]}. {m.family_name}")
            if len(words) >= 3:
                # compound surnames print as the last two words
                compound = " ".join(words[-2:])
                forms.add(compound)
                forms.add(f"{compound}, {first[0]}.")
                forms.add(f"{first[0]}. {compound}")
            for form in forms:
                key = (m.chamber, _normalize(form))
                bucket = self._index.setdefault(key, [])
                if m not in bucket:
                    bucket.append(m)

    def resolve(self, name: str, chamber: str) -> Member:
        key = _normalize(name)
        cached = self._resolved.get((chamber, key))
        if cached is not None:
            return cached
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
            self._resolved[(chamber, key)] = candidates[0]
            return candidates[0]
        if not candidates:
            raise UnmatchedNameError(f"{name!r} ({chamber}) matches no roster member")
        detail = ", ".join(f"{m.name} (district {m.district})" for m in candidates)
        raise AmbiguousNameError(f"{name!r} ({chamber}) is ambiguous: {detail}")

    def resolve_or_none(self, name: str, chamber: str) -> Member | None:
        """Lenient variant for sponsorships: None, never a guess."""
        try:
            return self.resolve(name, chamber)
        except (UnmatchedNameError, AmbiguousNameError):
            return None
