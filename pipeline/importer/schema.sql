-- Badger Politics — SQLite schema (the entire database; see docs plan §4).
-- Rebuilt nightly by the importer; read-only at serve time.

PRAGMA foreign_keys = ON;

CREATE TABLE sessions (
    id           TEXT PRIMARY KEY,
    identifier   TEXT NOT NULL UNIQUE,   -- odd year of the biennium, e.g. '2025'
    name         TEXT,
    start_date   TEXT,
    end_date     TEXT,
    -- full = actions + roll calls; partial = actions only (older sessions)
    data_quality TEXT CHECK (data_quality IN ('full', 'partial'))
);

CREATE TABLE people (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    party        TEXT,
    current_role TEXT,
    chamber      TEXT,
    district     INTEGER,
    image_url    TEXT,
    -- official Capitol office contacts (sitting members only), from each
    -- member's docs.legis page; never personal contacts
    email          TEXT,
    office_phone   TEXT,
    office_address TEXT,
    contact_url    TEXT
);

CREATE TABLE bills (
    id                       TEXT PRIMARY KEY,
    session_id               TEXT NOT NULL REFERENCES sessions (id),
    identifier               TEXT NOT NULL,   -- e.g. 'AB 656'
    title                    TEXT,
    chamber                  TEXT,
    classification           TEXT,
    -- derived: introduced|in_committee|passed_chamber|passed|enacted|vetoed|failed_sjr1
    status                   TEXT,
    latest_action_date       TEXT,
    latest_action_desc       TEXT,
    -- official bill-text page (text/html version link); LRB analysis source
    text_url                 TEXT,
    -- LRB plain-language analysis, extracted from the bill text page
    lrb_analysis             TEXT,
    -- the graveyard flag: referred, never heard, then failed pursuant to SJR 1
    died_without_hearing     INTEGER NOT NULL DEFAULT 0 CHECK (died_without_hearing IN (0, 1)),
    committee_at_death         TEXT,
    committee_chamber_at_death TEXT,
    committee_chair_at_death   TEXT,
    source                   TEXT CHECK (source IN ('openstates', 'legiscan', 'manual'))
);

CREATE TABLE sponsorships (
    bill_id        TEXT NOT NULL REFERENCES bills (id),
    person_id      TEXT REFERENCES people (id),   -- NULL when unresolvable (kept by name, never guessed)
    name           TEXT NOT NULL,                 -- as printed on the bill
    classification TEXT,
    is_primary     INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1))
);

CREATE TABLE actions (
    id             TEXT PRIMARY KEY,
    bill_id        TEXT NOT NULL REFERENCES bills (id),
    date           TEXT,
    chamber        TEXT,
    description    TEXT,
    classification TEXT
);

-- official documents attached to a bill (fiscal estimates, memos), with
-- the docs.legis note text verbatim and the official URL
CREATE TABLE bill_documents (
    bill_id TEXT NOT NULL REFERENCES bills (id),
    note    TEXT NOT NULL,
    url     TEXT NOT NULL
);
CREATE INDEX idx_bill_documents_bill ON bill_documents (bill_id);

-- service terms from the people files (recalls and resignations end
-- terms mid-biennium); out-of-office gaps must never count against or
-- toward a member
CREATE TABLE person_terms (
    person_id TEXT NOT NULL REFERENCES people (id),
    chamber   TEXT NOT NULL,
    district  INTEGER,
    start     TEXT NOT NULL,
    end       TEXT,
    end_label TEXT,  -- curated: why the term ended (term_events.json)
    end_url   TEXT   -- curated: a verified reference for that event
);
CREATE INDEX idx_person_terms_person ON person_terms (person_id);

-- WisconsinEye recordings matched to hearings by exact date + committee
-- title; metadata only, linking to their site
CREATE TABLE hearing_videos (
    hearing_id TEXT PRIMARY KEY REFERENCES hearings (id),
    url        TEXT NOT NULL,
    title      TEXT NOT NULL
);

-- the state's own subject index terms per bill, matched by exact
-- session + identifier only
CREATE TABLE bill_subjects (
    bill_id TEXT NOT NULL REFERENCES bills (id),
    subject TEXT NOT NULL
);
CREATE INDEX idx_bill_subjects_bill ON bill_subjects (bill_id);
CREATE INDEX idx_bill_subjects_subject ON bill_subjects (subject);

-- current committee rosters from the openstates people files; person ids
-- are exact, so membership inherits roster precision
CREATE TABLE committee_members (
    committee_id TEXT NOT NULL REFERENCES committees (id),
    person_id    TEXT NOT NULL REFERENCES people (id),
    role         TEXT NOT NULL
);
CREATE INDEX idx_committee_members_committee ON committee_members (committee_id);

CREATE TABLE vote_events (
    id         TEXT PRIMARY KEY,
    bill_id    TEXT NOT NULL REFERENCES bills (id),
    date       TEXT,
    chamber    TEXT,
    motion     TEXT,
    result     TEXT,
    yes_count  INTEGER,
    no_count   INTEGER,
    nv_count   INTEGER,
    source_url TEXT,
    source     TEXT
);

CREATE TABLE vote_records (
    vote_event_id TEXT NOT NULL REFERENCES vote_events (id),
    person_id     TEXT NOT NULL REFERENCES people (id),
    -- the full openstates vote-option vocabulary
    option        TEXT NOT NULL CHECK (option IN
        ('yes', 'no', 'not voting', 'excused', 'absent', 'abstain', 'paired', 'other'))
);

CREATE TABLE committees (
    id              TEXT PRIMARY KEY,
    chamber         TEXT,
    name            TEXT NOT NULL,
    chair_person_id TEXT REFERENCES people (id)
);

CREATE TABLE hearings (
    id                   TEXT PRIMARY KEY,
    title                TEXT,  -- event name; display fallback when no committee matches
    committee_id         TEXT REFERENCES committees (id),
    date                 TEXT,
    time                 TEXT,
    location             TEXT,
    agenda_bill_ids_json TEXT,
    source_url           TEXT
);

CREATE TABLE elections (
    person_id      TEXT NOT NULL REFERENCES people (id),
    cycle_year     INTEGER NOT NULL,
    office         TEXT,
    district       INTEGER,
    on_ballot      INTEGER CHECK (on_ballot IN (0, 1)),
    is_incumbent   INTEGER CHECK (is_incumbent IN (0, 1)),
    opponents_json TEXT,
    source         TEXT
);

-- Official WEC general-election results for legislative contests, summed
-- from ward-by-ward canvass spreadsheets. Display data (no FKs).
CREATE TABLE election_history (
    year       INTEGER NOT NULL,
    chamber    TEXT NOT NULL CHECK (chamber IN ('lower', 'upper')),
    district   INTEGER NOT NULL,
    candidate  TEXT NOT NULL,
    party      TEXT,
    votes      INTEGER NOT NULL,
    total_cast INTEGER  -- the contest's official Total Votes Cast, repeated per row
);
CREATE INDEX idx_election_history_seat ON election_history (chamber, district, year);

-- Statewide constitutional offices on the current ballot, straight from
-- the WEC ballot-access report (candidates, incumbents, non-candidacy).
CREATE TABLE statewide_races (
    office                 TEXT NOT NULL,
    incumbent              TEXT,
    incumbent_noncandidacy INTEGER NOT NULL CHECK (incumbent_noncandidacy IN (0, 1)),
    candidate              TEXT NOT NULL,
    party                  TEXT,
    ballot_status          TEXT,
    source                 TEXT NOT NULL
);

-- Official WEC general-election results for statewide contests, summed
-- from ward-by-ward canvass spreadsheets. Display data (no FKs).
CREATE TABLE statewide_history (
    year       INTEGER NOT NULL,
    office     TEXT NOT NULL,
    candidate  TEXT NOT NULL,
    party      TEXT,
    votes      INTEGER NOT NULL,
    total_cast INTEGER  -- the contest's official Total Votes Cast, repeated per row
);

-- Certified county aggregates for statewide contests, taken from the
-- canvass's own County Totals rows (all 72, summing exactly to the
-- statewide candidate totals - both gate-checked).
CREATE TABLE statewide_county_results (
    year      INTEGER NOT NULL,
    office    TEXT NOT NULL,
    county    TEXT NOT NULL,
    candidate TEXT NOT NULL,
    party     TEXT,
    votes     INTEGER NOT NULL
);

-- Organizations registered as lobbying on a bill (Ethics Commission's Eye
-- on Lobbying; registration of interest, NOT a for/against position).
CREATE TABLE lobbying_interests (
    bill_id      TEXT NOT NULL REFERENCES bills (id),
    principal_id INTEGER NOT NULL,
    principal    TEXT NOT NULL,
    source_url   TEXT
);
CREATE INDEX idx_lobbying_bill ON lobbying_interests (bill_id);

-- Which CFIS candidate committees belong to which legislator (verified
-- mapping; lets the site distinguish "unmapped" from "raised nothing").
CREATE TABLE cfis_committees (
    person_id TEXT NOT NULL REFERENCES people (id),
    entity_id INTEGER NOT NULL,
    committee TEXT NOT NULL
);
CREATE INDEX idx_cfis_committees_person ON cfis_committees (person_id);

-- Campaign contributions received by sitting legislators' candidate
-- committees, from the CFIS public API (see docs/money-research.md).
CREATE TABLE contributions (
    id                  INTEGER PRIMARY KEY,  -- CFIS transaction id
    person_id           TEXT NOT NULL REFERENCES people (id),
    committee_entity_id INTEGER NOT NULL,
    date                TEXT,
    amount              REAL NOT NULL,
    from_entity_id      INTEGER,  -- CFIS donor entity: collision-proof identity
    from_name           TEXT,
    from_type           TEXT,  -- Individual / Registrant / ...
    occupation          TEXT,
    category            TEXT
);
CREATE INDEX idx_contributions_person ON contributions (person_id, date);

-- CFIS committee registry: the type behind every filer and counterparty,
-- so a PAC, a conduit, and a party transfer are never conflated.
CREATE TABLE cf_committees (
    entity_id      INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    committee_type TEXT,
    assigned_id    TEXT   -- CFIS's own committee number
);
CREATE INDEX idx_cf_committees_type ON cf_committees (committee_type);

-- Money filed by committees that are not one candidate's own: PAC and
-- party receipts and spending, plus independent expenditures (which carry
-- a for/against stance and the race they target). Candidate-committee
-- receipts stay in `contributions` with their verified person mapping.
CREATE TABLE cf_transactions (
    id                   INTEGER PRIMARY KEY,  -- CFIS transaction id
    filer_entity_id      INTEGER NOT NULL,
    filer_type           TEXT,
    direction            TEXT CHECK (direction IN ('INCOMING', 'OUTGOING')),
    date                 TEXT,
    amount               REAL NOT NULL,
    other_entity_id      INTEGER,  -- counterparty: donor in, payee out
    other_name           TEXT,
    other_type           TEXT,
    -- express advocacy: FOR/AGAINST a named candidate in a named race
    stance               TEXT CHECK (stance IN ('FOR', 'AGAINST') OR stance IS NULL),
    related_name         TEXT,
    related_office       TEXT,
    related_district     TEXT,
    -- conduits pass earmarked money through: the true recipient
    final_recipient_id   INTEGER,
    final_recipient_name TEXT,
    purpose              TEXT,
    report_id            INTEGER,  -- the Commission's report this row was filed on
    report_name          TEXT
);
CREATE INDEX idx_cf_tx_filer ON cf_transactions (filer_entity_id, date);
CREATE INDEX idx_cf_tx_stance ON cf_transactions (stance);
CREATE INDEX idx_cf_tx_other ON cf_transactions (other_entity_id);

-- Council votes from local Legistar tenants (importer/local_registry.py;
-- research in docs/research/local-votes-2026-08.md). Attribution is the
-- tenant's own person id on every row; no name matching anywhere.
CREATE TABLE local_bodies (
    tenant     TEXT PRIMARY KEY,          -- Legistar client id
    slug       TEXT NOT NULL UNIQUE,      -- URL path segment
    city       TEXT NOT NULL,
    name       TEXT NOT NULL,             -- display name of the council
    insite_url TEXT NOT NULL,             -- the tenant's public Legistar site
    seats      INTEGER NOT NULL
);

CREATE TABLE local_members (
    tenant      TEXT NOT NULL REFERENCES local_bodies (tenant),
    person_id   INTEGER NOT NULL,         -- the tenant's own id: the vote join key
    name        TEXT NOT NULL,            -- as shown: the person record's full name
                                          -- where the office record abbreviates
    record_name TEXT,                     -- the office record's own string
    slug        TEXT NOT NULL,
    -- aldermanic district; NULL where not recorded (a presiding mayor, or
    -- a historical member with no curated seat)
    seat        INTEGER,
    seat_basis  TEXT,                     -- curation source URL when curated
    member_type TEXT,                     -- the tenant's own label (Member/Chair)
    is_current  INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
    -- official portrait and office contacts, from the city's own page for
    -- the seat (image_basis) or the tenant's person record; NULL = none
    -- attributable under the exact rules in import_local
    image_url   TEXT,
    image_basis TEXT,
    email       TEXT,
    phone       TEXT,
    PRIMARY KEY (tenant, person_id)
);

-- every body a sitting member serves on, from the tenant's office records
CREATE TABLE local_memberships (
    tenant    TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    body_id   INTEGER NOT NULL,
    body_name TEXT NOT NULL,
    role      TEXT,
    start     TEXT,
    end       TEXT,
    body_url  TEXT,                       -- the tenant's public page for the body
    FOREIGN KEY (tenant, person_id) REFERENCES local_members (tenant, person_id)
);
CREATE INDEX idx_local_memberships ON local_memberships (tenant, person_id);

CREATE TABLE local_member_terms (
    tenant    TEXT NOT NULL,
    person_id INTEGER NOT NULL,
    title     TEXT,
    start     TEXT NOT NULL,
    end       TEXT,
    FOREIGN KEY (tenant, person_id) REFERENCES local_members (tenant, person_id)
);
CREATE INDEX idx_local_member_terms ON local_member_terms (tenant, person_id);

CREATE TABLE local_events (
    tenant         TEXT NOT NULL REFERENCES local_bodies (tenant),
    event_id       INTEGER NOT NULL,
    date           TEXT NOT NULL,
    minutes_status TEXT,
    insite_url     TEXT NOT NULL,         -- the clerk's public meeting page
    PRIMARY KEY (tenant, event_id)
);

CREATE TABLE local_actions (
    tenant        TEXT NOT NULL,
    event_item_id INTEGER NOT NULL,
    event_id      INTEGER NOT NULL,
    matter_id     INTEGER,
    matter_file   TEXT,
    matter_type   TEXT,
    matter_status TEXT,
    title         TEXT,
    action        TEXT NOT NULL,          -- what the body did, verbatim
    passed        INTEGER,                -- the clerk's own flag; may be NULL
    agenda_number TEXT,
    matter_url    TEXT,                   -- the clerk's public legislation page
    PRIMARY KEY (tenant, event_item_id),
    FOREIGN KEY (tenant, event_id) REFERENCES local_events (tenant, event_id)
);
CREATE INDEX idx_local_actions_event  ON local_actions (tenant, event_id);
CREATE INDEX idx_local_actions_matter ON local_actions (tenant, matter_id);

CREATE TABLE local_votes (
    tenant        TEXT NOT NULL,
    event_item_id INTEGER NOT NULL,
    person_id     INTEGER NOT NULL,
    value         TEXT NOT NULL,          -- Aye/No/Excused/... exactly as recorded
    PRIMARY KEY (tenant, event_item_id, person_id),
    FOREIGN KEY (tenant, event_item_id) REFERENCES local_actions (tenant, event_item_id),
    FOREIGN KEY (tenant, person_id) REFERENCES local_members (tenant, person_id)
);
CREATE INDEX idx_local_votes_person ON local_votes (tenant, person_id);

-- each tenant's own vote vocabulary (its VoteTypes), the checks' allowlist
CREATE TABLE local_vote_types (
    tenant TEXT NOT NULL,
    value  TEXT NOT NULL,
    PRIMARY KEY (tenant, value)
);

-- Build metadata, e.g. key='data_through' for the site footer freshness badge.
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX idx_bills_session          ON bills (session_id);
CREATE INDEX idx_bills_status           ON bills (session_id, status);
CREATE INDEX idx_sponsorships_bill      ON sponsorships (bill_id);
CREATE INDEX idx_sponsorships_person    ON sponsorships (person_id);
CREATE INDEX idx_actions_bill           ON actions (bill_id);
CREATE INDEX idx_vote_events_bill       ON vote_events (bill_id);
CREATE INDEX idx_vote_records_event     ON vote_records (vote_event_id);
CREATE INDEX idx_vote_records_person    ON vote_records (person_id);
CREATE INDEX idx_hearings_committee     ON hearings (committee_id);
CREATE INDEX idx_elections_cycle        ON elections (cycle_year);
