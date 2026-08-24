"""Read-only data-propagation audit, run on demand (not a deploy gate):
hunts the defect classes found in Aug 2026 (phantom coverage, silent-tail
terms, misattribution, mapping drift) plus gate blind spots.

Usage: uv run python audit.py [sqlite_path]
"""
import sqlite3
import sys

db = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "../data/wi.sqlite")
db.row_factory = sqlite3.Row
FULL = "'2011','2013','2015','2017','2019','2021','2023','2025','2026s1'"

db.executescript("""
CREATE TEMP TABLE pv AS
  SELECT DISTINCT r.person_id, e.chamber, substr(e.date,1,10) AS d
  FROM vote_records r JOIN vote_events e ON e.id = r.vote_event_id
  WHERE e.date IS NOT NULL AND e.chamber IN ('lower','upper');
CREATE INDEX temp.idx_pv ON pv (person_id, chamber, d);
CREATE TEMP TABLE cd AS
  SELECT DISTINCT chamber, substr(date,1,10) AS d FROM vote_events
  WHERE date IS NOT NULL AND chamber IN ('lower','upper');
CREATE INDEX temp.idx_cd ON cd (chamber, d);
CREATE TEMP TABLE lv AS
  SELECT person_id, chamber, MAX(d) AS last_vote FROM pv GROUP BY person_id, chamber;
""")


def check(title, rows, show=10):
    rows = list(rows)
    flag = "!!" if rows else "ok"
    print(f"[{flag}] {title}: {len(rows)}")
    for r in rows[:show]:
        print("      ", dict(r))
    return len(rows)


total = 0

# 1. chamber-blind gate gap: a vote in chamber C with no C-chamber term
total += check("votes whose chamber has no covering term (gate checks dates only)", db.execute("""
  SELECT p.name, pv.chamber, MIN(pv.d) first, MAX(pv.d) last, COUNT(*) days
  FROM pv JOIN people p ON p.id = pv.person_id
  WHERE NOT EXISTS (
    SELECT 1 FROM person_terms t WHERE t.person_id = pv.person_id AND t.chamber = pv.chamber
    AND pv.d >= t.start AND pv.d <= COALESCE(t.end,'9999'))
  GROUP BY pv.person_id, pv.chamber ORDER BY days DESC"""))

# 2. same person voting in both chambers on one day (definite misattribution)
total += check("same-day cross-chamber votes", db.execute("""
  SELECT p.name, a.d
  FROM pv a JOIN pv b ON a.person_id = b.person_id AND a.d = b.d
    AND a.chamber = 'lower' AND b.chamber = 'upper'
  JOIN people p ON p.id = a.person_id"""))

# 3. member records exist iff docs.legis published a roll-call document
#    (journal tally lines - committee exec sessions, procedural and
#    amendment motions - carry counts but no roll and never count toward
#    attendance). A /votes/ document without records is a scrape failure;
#    records without a document would be attribution from nowhere.
#    (zero-count events are attendance rolls - 2011's sv0001/sv0002 file
#    opening-day CALL OF ROLL under vote-document urls - not vote records)
total += check("vote events with a roll-call document but zero records", db.execute(f"""
  SELECT e.id, e.bill_id, e.date, e.source_url
  FROM vote_events e JOIN bills b ON b.id = e.bill_id
  WHERE b.session_id IN ({FULL}) AND e.source_url LIKE '%/votes/%'
  AND COALESCE(e.yes_count,0) + COALESCE(e.no_count,0) > 0
  AND NOT EXISTS (SELECT 1 FROM vote_records r WHERE r.vote_event_id = e.id)"""))
total += check("vote events with records but no roll-call document", db.execute(f"""
  SELECT e.id, e.bill_id, e.date, e.source_url
  FROM vote_events e JOIN bills b ON b.id = e.bill_id
  WHERE b.session_id IN ({FULL})
  AND (e.source_url IS NULL OR e.source_url NOT LIKE '%/votes/%')
  AND EXISTS (SELECT 1 FROM vote_records r WHERE r.vote_event_id = e.id)"""))

# 4. overlapping terms for one person+chamber (double coverage)
total += check("overlapping same-chamber terms", db.execute("""
  SELECT p.name, a.chamber, a.start s1, a.end e1, b.start s2, b.end e2
  FROM person_terms a JOIN person_terms b
    ON a.person_id = b.person_id AND a.chamber = b.chamber
    AND (a.start < b.start OR (a.start = b.start AND a.rowid < b.rowid))
  JOIN people p ON p.id = a.person_id
  WHERE b.start < COALESCE(a.end,'9999')"""))

# 5. simultaneous service in both chambers (beyond a 7-day transition)
total += check("concurrent cross-chamber service > 7 days", db.execute("""
  SELECT p.name, a.start s_lower, a.end e_lower, b.start s_upper, b.end e_upper
  FROM person_terms a JOIN person_terms b ON a.person_id = b.person_id
    AND a.chamber = 'lower' AND b.chamber = 'upper'
  JOIN people p ON p.id = a.person_id
  WHERE julianday(MIN(COALESCE(a.end,'9999-01-01'), COALESCE(b.end,'9999-01-01')))
      - julianday(MAX(a.start, b.start)) > 7"""))

# 6. former members with open-ended terms (phantom "still serving")
total += check("non-sitting people with open-ended terms", db.execute("""
  SELECT p.name, p.current_role, t.chamber, t.start
  FROM person_terms t JOIN people p ON p.id = t.person_id
  WHERE t.end IS NULL AND p.current_role NOT IN ('Representative','Senator')"""))

# 7. phantom coverage: a full-corpus biennium slice of a term with zero votes
#    cast while that chamber held >20 vote days inside the slice (Billings class)
total += check("covered biennium slice with zero votes despite 20+ chamber days", db.execute("""
  WITH biennia(by, s, e) AS (VALUES
    ('2011','2011-01-01','2013-01-01'),('2013','2013-01-01','2015-01-01'),
    ('2015','2015-01-01','2017-01-01'),('2017','2017-01-01','2019-01-01'),
    ('2019','2019-01-01','2021-01-01'),('2021','2021-01-01','2023-01-01'),
    ('2023','2023-01-01','2025-01-01'))
  SELECT p.name, t.chamber, b.by,
    MAX(t.start, b.s) slice_start, MIN(COALESCE(t.end,'9999'), b.e) slice_end
  FROM person_terms t JOIN people p ON p.id = t.person_id
  JOIN biennia b ON t.start < b.e AND b.s < COALESCE(t.end,'9999')
  WHERE NOT EXISTS (
    SELECT 1 FROM pv WHERE pv.person_id = t.person_id AND pv.chamber = t.chamber
    AND pv.d >= MAX(t.start, b.s) AND pv.d < MIN(COALESCE(t.end,'9999'), b.e))
  AND (SELECT COUNT(*) FROM cd WHERE cd.chamber = t.chamber
       AND cd.d >= MAX(t.start, b.s) AND cd.d < MIN(COALESCE(t.end,'9999'), b.e)) > 20
  GROUP BY t.person_id, t.chamber, b.by"""))

# 8. long silent tails: a final term in a chamber ends >120 days after the
#    person's last vote there while the chamber voted 20+ more days
total += check("terms extending far past last vote while chamber voted on", db.execute("""
  SELECT p.name, t.chamber, t.start, t.end, lv.last_vote,
    (SELECT COUNT(*) FROM cd WHERE cd.chamber = t.chamber
     AND cd.d > lv.last_vote AND cd.d < t.end) days_after
  FROM person_terms t
  JOIN lv ON lv.person_id = t.person_id AND lv.chamber = t.chamber
  JOIN people p ON p.id = t.person_id
  WHERE t.end IS NOT NULL AND t.end <= date('now')
  AND lv.last_vote < date(t.end, '-120 days')
  AND NOT EXISTS (SELECT 1 FROM person_terms t2 WHERE t2.person_id = t.person_id
                  AND t2.chamber = t.chamber AND t2.start > t.start)
  AND (SELECT COUNT(*) FROM cd WHERE cd.chamber = t.chamber
       AND cd.d > lv.last_vote AND cd.d < t.end) > 20"""))

# 9. money: recipients whose receipts are 100% outside their terms
total += check("contribution recipients with zero in-term receipts", db.execute("""
  SELECT p.name, COUNT(*) n, MIN(c.date) first, MAX(c.date) last
  FROM contributions c JOIN people p ON p.id = c.person_id
  GROUP BY c.person_id
  HAVING SUM(EXISTS (SELECT 1 FROM person_terms t WHERE t.person_id = c.person_id
    AND c.date >= t.start AND c.date <= COALESCE(t.end,'9999'))) = 0"""))

# 10. stale CFIS committee map: mapped people who are not sitting
total += check("cfis committee map entries for non-sitting people", db.execute("""
  SELECT p.name, p.current_role, m.committee
  FROM cfis_committees m JOIN people p ON p.id = m.person_id
  WHERE p.current_role NOT IN ('Representative','Senator')"""))

# 11. committee members who are not sitting members
total += check("current committee rosters listing non-sitting people", db.execute("""
  SELECT DISTINCT p.name, p.current_role, c.name committee
  FROM committee_members m JOIN people p ON p.id = m.person_id
  JOIN committees c ON c.id = m.committee_id
  WHERE p.current_role NOT IN ('Representative','Senator')"""))

# 11b. statewide data: candidate rows and history stay within the five
#      constitutional offices, with sane certified-turnout totals
total += check("statewide rows outside the five constitutional offices", db.execute("""
  SELECT office, COUNT(*) n FROM (
    SELECT office FROM statewide_races
    UNION ALL
    SELECT CASE WHEN office = 'GOVERNOR / LIEUTENANT GOVERNOR' THEN 'GOVERNOR'
                ELSE office END FROM statewide_history)
  WHERE office NOT IN ('GOVERNOR', 'LIEUTENANT GOVERNOR', 'ATTORNEY GENERAL',
                       'SECRETARY OF STATE', 'STATE TREASURER')
  GROUP BY office"""))
total += check("statewide contests below real-canvass turnout", db.execute("""
  SELECT year, office, COUNT(*) candidates, SUM(votes) total
  FROM statewide_history GROUP BY year, office
  HAVING COUNT(*) < 2 OR SUM(votes) < 500000"""))
total += check("statewide contests missing any of the 72 counties", db.execute("""
  SELECT year, office, COUNT(DISTINCT county) n FROM statewide_county_results
  GROUP BY year, office HAVING n != 72"""))
total += check("county sums that disagree with certified statewide totals", db.execute("""
  SELECT h.year, h.office, h.candidate, h.votes statewide, SUM(c.votes) county_sum
  FROM statewide_history h
  JOIN statewide_county_results c
    ON c.year = h.year AND c.office = h.office AND c.candidate = h.candidate
  GROUP BY h.year, h.office, h.candidate HAVING county_sum != h.votes"""))
total += check("official total_cast below the candidate sum", db.execute("""
  SELECT year, chamber, district FROM election_history
  WHERE total_cast IS NOT NULL
  GROUP BY year, chamber, district HAVING MAX(total_cast) < SUM(votes)"""))
# every contest winner must share a surname with someone recorded as
# seated in that seat a month into the new term (nicknames differ;
# surnames don't). Catches misparsed contests and phantom terms alike.
def _surname(name):
    return "".join(ch for ch in name.split()[-1].lower() if ch.isalpha())


winner_orphans = []
for year, chamber, district, candidate in db.execute("""
  SELECT year, chamber, district, candidate FROM (
    SELECT year, chamber, district, candidate,
           RANK() OVER (PARTITION BY year, chamber, district ORDER BY votes DESC) rk
    FROM election_history) WHERE rk = 1"""):
    seated = [r[0] for r in db.execute("""
      SELECT p.name FROM person_terms t JOIN people p ON p.id = t.person_id
      WHERE t.chamber = ? AND t.district = ?
      AND t.start <= ? AND COALESCE(t.end, '9999') >= ?""",
      (chamber, district, f"{year + 1}-02-01", f"{year + 1}-02-01"))]
    cand_squash = "".join(ch for ch in candidate.lower() if ch.isalpha())
    if not any(
        _surname(s) in cand_squash or cand_squash.endswith(_surname(s)[-6:])
        for s in seated
        if _surname(s)
    ):
        winner_orphans.append(
            {"year": year, "seat": f"{chamber} {district}",
             "winner": candidate, "seated": "; ".join(seated) or "(nobody)"}
        )
flag = "!!" if winner_orphans else "ok"
print(f"[{flag}] election winners never seated in the seat they won: {len(winner_orphans)}")
for w in winner_orphans[:10]:
    print("      ", w)
total += len(winner_orphans)

# 12. elections rows for non-sitting people
total += check("election rows for non-sitting people", db.execute("""
  SELECT p.name, p.current_role, e.cycle_year
  FROM elections e JOIN people p ON p.id = e.person_id
  WHERE p.current_role NOT IN ('Representative','Senator')"""))

# 13. (info) died-without-hearing bills on a same-biennium agenda: the
#    official bill history is the authority (no "public hearing held"
#    action), so these are notices for hearings never actually held on
#    that bill - listed for review, not counted as defects
print("[..] died_without_hearing bills on a same-biennium agenda notice (info)")
for r in db.execute("""
  SELECT b.id, b.identifier, h.date
  FROM bills b JOIN hearings h
    ON h.agenda_bill_ids_json LIKE '%"' || b.identifier || '"%'
    AND h.committee_id IS NOT NULL
  WHERE b.died_without_hearing = 1
  AND h.date >= substr(b.session_id,1,4) || '-01-01'
  AND h.date < CAST(CAST(substr(b.session_id,1,4) AS INT) + 2 AS TEXT) || '-01-01'"""):
    print("      ", dict(r))

# 14. sponsorship resolution rate per full session (dips = roster gaps)
print("[..] sponsorship person-resolution rate by session (info)")
for r in db.execute(f"""
  SELECT b.session_id, COUNT(*) n,
    ROUND(100.0 * SUM(s.person_id IS NOT NULL) / COUNT(*), 1) pct
  FROM sponsorships s JOIN bills b ON b.id = s.bill_id
  WHERE b.session_id IN ({FULL}) GROUP BY b.session_id ORDER BY b.session_id"""):
    print(f"       {r['session_id']}: {r['pct']}% of {r['n']}")

# 15. duplicate people: same normalized name, different ids
total += check("distinct person ids sharing a normalized name", db.execute("""
  SELECT a.name, a.id id1, b.id id2
  FROM people a JOIN people b ON a.id < b.id
  AND LOWER(REPLACE(REPLACE(a.name,'.',''),' ',''))
    = LOWER(REPLACE(REPLACE(b.name,'.',''),' ',''))"""))

print(f"\nTOTAL flagged rows: {total}")
