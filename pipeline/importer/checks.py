"""Integrity gates run after every import; a failure aborts the deploy.
Hard rule: never weaken a gate to make a run pass.

Usage: python -m importer.checks <sqlite_path> [--counts-file PATH]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

TOLERANCE_FRACTION = 0.02  # allow a 2% dip (e.g. scraper-side dedupe changes)


def check_vote_counts(conn: sqlite3.Connection) -> list[str]:
    failures = []
    rows = conn.execute(
        """
        SELECT e.id, e.yes_count, e.no_count, e.nv_count,
               SUM(CASE WHEN r.option = 'yes' THEN 1 ELSE 0 END),
               SUM(CASE WHEN r.option = 'no' THEN 1 ELSE 0 END),
               SUM(CASE WHEN r.option NOT IN ('yes', 'no') THEN 1 ELSE 0 END)
        FROM vote_events e
        JOIN vote_records r ON r.vote_event_id = e.id
        GROUP BY e.id
        """
    ).fetchall()
    for event_id, yes_c, no_c, nv_c, yes_r, no_r, nv_r in rows:
        # yes/no reconcile exactly (they decide outcomes); NV is all-or-none
        # because docs.legis sometimes omits the NV name list entirely
        # (2013 sv0012) — partial NV parses still fail, see patches/0002
        problems = (yes_c or 0) != yes_r or (no_c or 0) != no_r
        if nv_r != 0 and nv_r != (nv_c or 0):
            problems = True
        if problems:
            failures.append(
                f"vote {event_id}: stored counts y/n/nv="
                f"{(yes_c or 0, no_c or 0, nv_c or 0)} but records="
                f"{(yes_r, no_r, nv_r)}"
            )
    if not rows:
        failures.append("no vote events have individual vote records at all")
    return failures


def check_bill_counts(conn: sqlite3.Connection, counts_file: Path) -> list[str]:
    current = dict(
        conn.execute("SELECT session_id, COUNT(*) FROM bills GROUP BY session_id")
    )
    if not current:
        return ["bills table is empty"]
    previous = {}
    if counts_file.exists():
        previous = json.loads(counts_file.read_text(encoding="utf-8"))
    failures = []
    for session_id, prev_count in previous.items():
        now = current.get(session_id, 0)
        floor = int(prev_count * (1 - TOLERANCE_FRACTION))
        if now < floor:
            failures.append(
                f"session {session_id}: bill count fell {prev_count} -> {now}"
                f" (floor {floor}) — scrape looks broken"
            )
    if not failures:
        counts_file.write_text(json.dumps(current, indent=1), encoding="utf-8")
    return failures


def check_referential_integrity(conn: sqlite3.Connection) -> list[str]:
    queries = {
        "vote_records -> people": (
            "SELECT COUNT(*) FROM vote_records r"
            " LEFT JOIN people p ON p.id = r.person_id WHERE p.id IS NULL"
        ),
        "vote_records -> vote_events": (
            "SELECT COUNT(*) FROM vote_records r"
            " LEFT JOIN vote_events e ON e.id = r.vote_event_id WHERE e.id IS NULL"
        ),
        "vote_events -> bills": (
            "SELECT COUNT(*) FROM vote_events e"
            " LEFT JOIN bills b ON b.id = e.bill_id WHERE b.id IS NULL"
        ),
        "bills -> sessions": (
            "SELECT COUNT(*) FROM bills b"
            " LEFT JOIN sessions s ON s.id = b.session_id WHERE s.id IS NULL"
        ),
        "actions -> bills": (
            "SELECT COUNT(*) FROM actions a"
            " LEFT JOIN bills b ON b.id = a.bill_id WHERE b.id IS NULL"
        ),
        "sponsorships -> bills": (
            "SELECT COUNT(*) FROM sponsorships sp"
            " LEFT JOIN bills b ON b.id = sp.bill_id WHERE b.id IS NULL"
        ),
        "sponsorships -> people (when resolved)": (
            "SELECT COUNT(*) FROM sponsorships sp LEFT JOIN people p ON p.id = sp.person_id"
            " WHERE sp.person_id IS NOT NULL AND p.id IS NULL"
        ),
        "contributions -> people": (
            "SELECT COUNT(*) FROM contributions c"
            " LEFT JOIN people p ON p.id = c.person_id WHERE p.id IS NULL"
        ),
        # every receipt must trace to a live (committee, person) mapping;
        # a stale archive after a map change is a misattribution risk
        "contributions -> committee mapping": (
            "SELECT COUNT(*) FROM contributions c LEFT JOIN cfis_committees m"
            " ON m.entity_id = c.committee_entity_id AND m.person_id = c.person_id"
            " WHERE m.entity_id IS NULL"
        ),
        "one committee mapped to two people": (
            "SELECT COUNT(*) FROM (SELECT entity_id FROM cfis_committees"
            " GROUP BY entity_id HAVING COUNT(DISTINCT person_id) > 1)"
        ),
        "same person twice on one roll call": (
            "SELECT COUNT(*) FROM (SELECT vote_event_id, person_id FROM vote_records"
            " GROUP BY vote_event_id, person_id HAVING COUNT(*) > 1)"
        ),
        "hearing chairs -> people": (
            "SELECT COUNT(*) FROM committees c LEFT JOIN people p ON p.id = c.chair_person_id"
            " WHERE c.chair_person_id IS NOT NULL AND p.id IS NULL"
        ),
        # the official history names cosponsors at introduction; every such
        # bill must carry cosponsor rows (derived when the scraper drops them)
        "bills whose introduction names cosponsors but carry none": (
            "SELECT COUNT(DISTINCT a.bill_id) FROM actions a"
            " WHERE a.description LIKE 'Introduced by%cosponsored by%'"
            " AND NOT EXISTS (SELECT 1 FROM sponsorships s"
            "   WHERE s.bill_id = a.bill_id AND s.classification = 'cosponsor')"
            " AND NOT EXISTS (SELECT 1 FROM actions w WHERE w.bill_id = a.bill_id"
            "   AND w.description LIKE '%withdrawn as a cosponsor%')"
        ),
        # an event with no counts and no records shows nothing and can only
        # cite a document that isn't a vote (see import_vote_event)
        "vote events with all-zero counts and no records": (
            "SELECT COUNT(*) FROM vote_events e"
            " WHERE COALESCE(yes_count,0)=0 AND COALESCE(no_count,0)=0"
            " AND COALESCE(nv_count,0)=0 AND NOT EXISTS"
            " (SELECT 1 FROM vote_records r WHERE r.vote_event_id = e.id)"
        ),
        # every committee transaction must trace to a known filer, or the
        # money is attributed to a committee we cannot name
        "cf transactions -> committee registry": (
            "SELECT COUNT(*) FROM cf_transactions t LEFT JOIN cf_committees c"
            " ON c.entity_id = t.filer_entity_id WHERE c.entity_id IS NULL"
        ),
        # express advocacy is a claim about a named candidate: a stance with
        # no target is unattributable and must never render
        # A stance alone does not make a row candidate advocacy: referendum
        # committees advocate on ballot questions, and parties/PACs flag
        # ordinary vendor payments the same way. Both legitimately name no
        # candidate, so requiring one would fail on correct data. What does
        # hold — and what the display depends on — is that the candidate and
        # the race travel together: a row naming either names both.
        # scoped to third-party filers: those are the rows shown as
        # independent expenditure. A candidate committee's own stanced
        # spending is never presented that way, so its gaps cannot mislead.
        "advocacy naming a race but not the candidate": (
            "SELECT COUNT(*) FROM cf_transactions WHERE stance IS NOT NULL"
            " AND related_office IS NOT NULL"
            " AND (related_name IS NULL OR related_name = '')"
            " AND COALESCE(filer_type, '') NOT IN ('State Candidate', 'Federal Candidate')"
        ),
        "advocacy naming a candidate but not the race": (
            "SELECT COUNT(*) FROM cf_transactions WHERE stance IS NOT NULL"
            " AND related_name IS NOT NULL AND related_office IS NULL"
            " AND COALESCE(filer_type, '') NOT IN ('State Candidate', 'Federal Candidate')"
        ),
        # a conduit pass-through whose final recipient is missing would be
        # shown as the conduit's own money
        "conduit rows with no final recipient": (
            "SELECT COUNT(*) FROM cf_transactions"
            " WHERE filer_type = 'Conduit' AND direction = 'OUTGOING'"
            " AND (final_recipient_name IS NULL OR final_recipient_name = '')"
        ),
        # statewide rows only ever carry the five constitutional offices,
        # and a parsed statewide contest below real turnout is a bad parse
        "statewide races carry only known offices": (
            "SELECT COUNT(*) FROM statewide_races WHERE office NOT IN"
            " ('GOVERNOR', 'LIEUTENANT GOVERNOR', 'ATTORNEY GENERAL',"
            "  'SECRETARY OF STATE', 'STATE TREASURER')"
        ),
        "statewide history contests look like real canvasses": (
            "SELECT COUNT(*) FROM (SELECT year, office FROM statewide_history"
            " GROUP BY year, office"
            " HAVING COUNT(*) < 2 OR SUM(votes) < 500000)"
        ),
        # resolutions never go to the governor; a governor-implying status
        # on one is a derivation bug (compound classifications fail loudly)
        "resolutions never carry governor statuses": (
            "SELECT COUNT(*) FROM bills WHERE classification != 'bill'"
            " AND status IN ('enacted', 'vetoed', 'passed')"
        ),
        "no vote outside a recorded term": (
            "SELECT COUNT(*) FROM vote_records r"
            " JOIN vote_events e ON e.id = r.vote_event_id"
            " WHERE e.date IS NOT NULL AND NOT EXISTS ("
            "   SELECT 1 FROM person_terms t WHERE t.person_id = r.person_id"
            "   AND e.date >= t.start AND e.date <= COALESCE(t.end, '9999'))"  # roster.OPEN_END
        ),
        "person_terms -> people": (
            "SELECT COUNT(*) FROM person_terms t"
            " LEFT JOIN people p ON p.id = t.person_id WHERE p.id IS NULL"
        ),
        # office contacts come from docs.legis member pages; a sitting member
        # without one means the contact fetch or parse broke
        "sitting members missing office contact info": (
            "SELECT COUNT(*) FROM people WHERE current_role IN"
            " ('Representative', 'Senator')"
            " AND (email IS NULL OR office_phone IS NULL)"
        ),
        "every sitting member has a live term": (
            "SELECT COUNT(*) FROM people WHERE current_role IN"
            " ('Representative', 'Senator') AND id NOT IN"
            " (SELECT person_id FROM person_terms"
            "  WHERE end IS NULL OR end >= date('now'))"
        ),
        "hearing_videos -> hearings": (
            "SELECT COUNT(*) FROM hearing_videos v"
            " LEFT JOIN hearings h ON h.id = v.hearing_id WHERE h.id IS NULL"
        ),
        "bill_subjects -> bills": (
            "SELECT COUNT(*) FROM bill_subjects s"
            " LEFT JOIN bills b ON b.id = s.bill_id WHERE b.id IS NULL"
        ),
        "bill_documents -> bills": (
            "SELECT COUNT(*) FROM bill_documents d"
            " LEFT JOIN bills b ON b.id = d.bill_id WHERE b.id IS NULL"
        ),
        "committee_members -> committees": (
            "SELECT COUNT(*) FROM committee_members m"
            " LEFT JOIN committees c ON c.id = m.committee_id WHERE c.id IS NULL"
        ),
        "committee_members -> people": (
            "SELECT COUNT(*) FROM committee_members m"
            " LEFT JOIN people p ON p.id = m.person_id WHERE p.id IS NULL"
        ),
    }
    failures = []
    for label, query in queries.items():
        orphans = conn.execute(query).fetchone()[0]
        if orphans:
            failures.append(f"{label}: {orphans} orphaned rows")
    return failures


def check_federal(conn: sqlite3.Connection) -> list[str]:
    """Federal tables are an enrichment; when present they must hold the
    same invariants the importer enforced: stated tallies equal counted
    positions, and every Senate vote carries exactly two WI senators."""
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='federal_votes'"
    ).fetchone()
    if not has:
        return []
    failures = []
    # senate rows hold the full chamber, so tallies can be recounted; house
    # rows are WI-only by design, so only their bounds can be checked here
    # (their tallies were reconciled against the full roll at import)
    bad = conn.execute(
        """SELECT v.id FROM federal_votes v JOIN federal_vote_records r
             ON r.vote_id = v.id
           WHERE v.chamber = 'senate'
           GROUP BY v.id
           HAVING SUM(r.vote_cast IN ('Yea', 'Guilty')) != v.yeas
               OR SUM(r.vote_cast IN ('Nay', 'Not Guilty')) != v.nays
               OR SUM(r.state = 'WI') != 2"""
    ).fetchall()
    bad += conn.execute(
        """SELECT v.id FROM federal_votes v JOIN federal_vote_records r
             ON r.vote_id = v.id
           WHERE v.chamber = 'house'
           GROUP BY v.id
           HAVING COUNT(*) < 1 OR COUNT(*) > 10 OR SUM(r.state != 'WI') > 0"""
    ).fetchall()
    for (vote_id,) in bad:
        failures.append(f"federal vote {vote_id}: tally or WI-count mismatch")
    members = conn.execute("SELECT COUNT(*) FROM federal_members").fetchone()[0]
    if members != 10:
        failures.append(f"federal_members holds {members} rows, expected 10")
    return failures


def check_local(conn: sqlite3.Connection) -> list[str]:
    """Local council votes are an enrichment; when the tables are present
    they must hold what the importer promised: every vote traces to the
    tenant's own member id and vocabulary, every record links its public
    page, and every sitting alderperson has a seat."""
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_bodies'"
    ).fetchone()
    if not has or not conn.execute("SELECT 1 FROM local_bodies").fetchone():
        return []
    queries = {
        "local votes -> actions": (
            "SELECT COUNT(*) FROM local_votes v LEFT JOIN local_actions a"
            " ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id"
            " WHERE a.event_item_id IS NULL"
        ),
        "local votes -> members": (
            "SELECT COUNT(*) FROM local_votes v LEFT JOIN local_members m"
            " ON m.tenant = v.tenant AND m.person_id = v.person_id"
            " WHERE m.person_id IS NULL"
        ),
        "local actions -> events": (
            "SELECT COUNT(*) FROM local_actions a LEFT JOIN local_events e"
            " ON e.tenant = a.tenant AND e.event_id = a.event_id"
            " WHERE e.event_id IS NULL"
        ),
        # a value outside the tenant's own VoteTypes is platform drift
        "local vote values outside the tenant's vocabulary": (
            "SELECT COUNT(*) FROM local_votes v LEFT JOIN local_vote_types t"
            " ON t.tenant = v.tenant AND t.value = v.value WHERE t.value IS NULL"
        ),
        "local events missing their public page": (
            "SELECT COUNT(*) FROM local_events"
            " WHERE insite_url IS NULL OR insite_url = ''"
        ),
        # the mayor presides without a seat; every sitting *Member* has one
        "sitting council members missing a seat": (
            "SELECT COUNT(*) FROM local_members WHERE is_current = 1"
            " AND member_type = 'Member' AND seat IS NULL"
        ),
        "local memberships -> members": (
            "SELECT COUNT(*) FROM local_memberships s LEFT JOIN local_members m"
            " ON m.tenant = s.tenant AND m.person_id = s.person_id"
            " WHERE m.person_id IS NULL"
        ),
        "local roll calls -> events": (
            "SELECT COUNT(*) FROM local_rollcalls r LEFT JOIN local_events e"
            " ON e.tenant = r.tenant AND e.event_id = r.event_id"
            " WHERE e.event_id IS NULL"
        ),
        "local roll calls -> members": (
            "SELECT COUNT(*) FROM local_rollcalls r LEFT JOIN local_members m"
            " ON m.tenant = r.tenant AND m.person_id = r.person_id"
            " WHERE m.person_id IS NULL"
        ),
        "local roll-call values outside the tenant's vocabulary": (
            "SELECT COUNT(*) FROM local_rollcalls r LEFT JOIN local_vote_types t"
            " ON t.tenant = r.tenant AND t.value = r.value WHERE t.value IS NULL"
        ),
        "duplicate local member slugs": (
            "SELECT COUNT(*) FROM (SELECT tenant, slug FROM local_members"
            " GROUP BY tenant, slug HAVING COUNT(*) > 1)"
        ),
        # a tenant with only Ayes means the fetch stopped at consent items
        "local tenants with no dissenting vote on record": (
            "SELECT COUNT(*) FROM local_bodies b WHERE NOT EXISTS"
            " (SELECT 1 FROM local_votes v WHERE v.tenant = b.tenant"
            "  AND v.value = 'No')"
        ),
    }
    failures = []
    for label, query in queries.items():
        bad = conn.execute(query).fetchone()[0]
        if bad:
            failures.append(f"{label}: {bad} rows")
    return failures


def run_checks(db_path: Path, counts_file: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        failures = check_vote_counts(conn)
        failures += check_bill_counts(conn, counts_file)
        failures += check_referential_integrity(conn)
        failures += check_federal(conn)
        failures += check_local(conn)
    finally:
        conn.close()
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--counts-file", type=Path)
    ns = parser.parse_args(argv)
    counts_file = ns.counts_file or ns.db_path.parent / ".bill_counts.json"
    failures = run_checks(ns.db_path, counts_file)
    if failures:
        for failure in failures:
            print(f"CHECK FAILED: {failure}", file=sys.stderr)
        return 1
    print("all integrity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
