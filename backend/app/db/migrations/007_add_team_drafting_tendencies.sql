-- Store auditable team drafting preferences derived from historical selections.
CREATE TABLE IF NOT EXISTS team_drafting_tendencies (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    draft_year INTEGER,
    tendency_type VARCHAR(40) NOT NULL,
    position_code VARCHAR(20),
    metric_name VARCHAR(60),
    target_value VARCHAR(150),
    minimum_value NUMERIC(8, 2),
    maximum_value NUMERIC(8, 2),
    preference_score NUMERIC(5, 2) NOT NULL CHECK (preference_score >= 0 AND preference_score <= 100),
    confidence_score NUMERIC(5, 2) NOT NULL DEFAULT 0 CHECK (confidence_score >= 0 AND confidence_score <= 100),
    sample_size INTEGER NOT NULL DEFAULT 0 CHECK (sample_size >= 0),
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    rationale VARCHAR(500),
    observed_at TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_team_tendencies_team_year
    ON team_drafting_tendencies(team_id, draft_year, is_active);