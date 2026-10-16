CREATE TABLE IF NOT EXISTS historical_draft_trades (
    id SERIAL PRIMARY KEY,
    draft_year INTEGER NOT NULL,
    pick_number INTEGER NOT NULL,
    moving_up_team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    moving_down_team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500),
    observed_at TIMESTAMP NOT NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_historical_trade_source_pick UNIQUE(source_name, draft_year, pick_number)
);

CREATE INDEX IF NOT EXISTS ix_historical_trades_year
    ON historical_draft_trades(draft_year, moving_up_team_id, moving_down_team_id);