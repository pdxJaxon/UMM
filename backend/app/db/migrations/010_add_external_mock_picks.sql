-- Store external mock selections for low-weight consensus analysis.
CREATE TABLE IF NOT EXISTS external_mock_picks (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    mock_id VARCHAR(150) NOT NULL,
    draft_year INTEGER NOT NULL,
    pick_number INTEGER NOT NULL,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    observed_at TIMESTAMP NOT NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_external_mock_lookup
    ON external_mock_picks(draft_year, team_id, pick_number);