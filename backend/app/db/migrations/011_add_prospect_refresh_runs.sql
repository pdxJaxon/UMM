-- Audit scheduled and manual prospect refresh outcomes.
CREATE TABLE IF NOT EXISTS prospect_refresh_runs (
    id SERIAL PRIMARY KEY,
    draft_year INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    source_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS ix_prospect_refresh_runs_year
    ON prospect_refresh_runs(draft_year, started_at);