-- Store auditable negative-issue records separately from player identity data.
CREATE TABLE IF NOT EXISTS player_derogatory_concerns (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    category VARCHAR(60) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL,
    confidence VARCHAR(20) NOT NULL DEFAULT 'reported',
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    occurred_at TIMESTAMP,
    reported_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_derogatory_player_id
    ON player_derogatory_concerns(player_id);