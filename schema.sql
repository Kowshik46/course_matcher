-- schema.sql — CREATE TABLE IF NOT EXISTS so init_db() is idempotent.
-- Percent values (min_eligibility_pct, placement_pct, qualification_pct)
-- are stored as 0-100 everywhere.  Money (fee_inr, budget_inr) is plain
-- integer rupees.

CREATE TABLE IF NOT EXISTS programs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    university          TEXT    NOT NULL,
    program_name        TEXT    NOT NULL,
    level               TEXT    NOT NULL,   -- bachelors | masters | certification
    specialization      TEXT    NOT NULL,   -- e.g. "Finance"
    mode                TEXT    NOT NULL,   -- online | offline | hybrid
    fee_inr             INTEGER NOT NULL,   -- total fee in ₹
    city                TEXT,               -- nullable for pure-online programs
    state               TEXT,               -- nullable for pure-online programs
    min_eligibility_pct REAL    NOT NULL,   -- 0-100; program's minimum qualifying %
    apply_url           TEXT,
    placement_pct       REAL,               -- 0-100; % of cohort placed
    -- 8 quality parameters, each 0-10
    brand_score         REAL,
    placements_score    REAL,
    course_depth_score  REAL,
    faculty_score       REAL,
    support_score       REAL,
    infra_score         REAL,
    accreditation_score REAL,
    qs_score            REAL,
    -- display fields
    approvals_text      TEXT,
    notes               TEXT,
    created_at          TEXT    DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS leads (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    age               INTEGER,
    city              TEXT,
    state             TEXT,
    level             TEXT,               -- desired level
    specialization    TEXT,               -- desired field e.g. "Finance"
    mode              TEXT,               -- online | offline | no_preference
    budget_inr        INTEGER,            -- plain integer rupees
    qualification_pct REAL,               -- 0-100
    reasons           TEXT,               -- CSV of selected reasons
    derived_income    INTEGER,            -- TODO: future use — captured but NOT used in filtering/scoring
    created_at        TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
