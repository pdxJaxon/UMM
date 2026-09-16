-- Store weighted, auditable meetings between teams and draft prospects.
CREATE TABLE IF NOT EXISTS team_prospect_meetings (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    draft_year INTEGER NOT NULL,
    meeting_type VARCHAR(60) NOT NULL,
    importance_score NUMERIC(5, 2) NOT NULL CHECK (importance_score >= 0 AND importance_score <= 100),
    occurred_at TIMESTAMP,
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    notes VARCHAR(500),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_team_prospect_meetings_lookup
    ON team_prospect_meetings(team_id, player_id, draft_year, is_active);