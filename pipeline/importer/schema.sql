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
    image_url    TEXT
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
