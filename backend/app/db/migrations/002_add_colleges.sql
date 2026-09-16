-- Add FBS college reference data support to an existing PostgreSQL database.
CREATE TABLE IF NOT EXISTS colleges (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    abbreviation VARCHAR(20) UNIQUE NOT NULL,
    conference VARCHAR(80) NOT NULL,
    division VARCHAR(20) NOT NULL DEFAULT 'FBS',
    logo_url VARCHAR(500) NOT NULL,
    official_url VARCHAR(500) NOT NULL
);

ALTER TABLE players ALTER COLUMN college_id TYPE VARCHAR(100);

-- Run `python -m app.db.initialize` to load college reference rows before
-- adding the foreign key in a later migration.