-- Store multiple role-specific needs per team and draft season.
CREATE TABLE IF NOT EXISTS team_needs (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    draft_year INTEGER NOT NULL,
    position_code VARCHAR(20) NOT NULL,
    role_level VARCHAR(30) NOT NULL,
    need_score NUMERIC(5, 2) NOT NULL CHECK (need_score >= 0 AND need_score <= 100),
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    rationale VARCHAR(500),
    observed_at TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_team_needs_team_year
    ON team_needs(team_id, draft_year, is_active);