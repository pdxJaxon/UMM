ALTER TABLE team_drafting_tendencies
    ADD COLUMN IF NOT EXISTS actor_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS actor_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS actor_name VARCHAR(150);

ALTER TABLE historical_draft_trades
    ADD COLUMN IF NOT EXISTS general_manager_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS general_manager_name VARCHAR(150),
    ADD COLUMN IF NOT EXISTS head_coach_id VARCHAR(120),
    ADD COLUMN IF NOT EXISTS head_coach_name VARCHAR(150);

CREATE TABLE IF NOT EXISTS team_leadership (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    role_type VARCHAR(20) NOT NULL,
    person_id VARCHAR(120) NOT NULL,
    person_name VARCHAR(150) NOT NULL,
    start_year INTEGER NOT NULL,
    end_year INTEGER,
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    observed_at TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_team_leadership_period UNIQUE(team_id, role_type, person_id, start_year)
);

CREATE INDEX IF NOT EXISTS ix_team_leadership_active
    ON team_leadership(team_id, role_type, start_year, end_year, is_active);
CREATE INDEX IF NOT EXISTS ix_tendency_actor
    ON team_drafting_tendencies(actor_type, actor_id, tendency_type, is_active);