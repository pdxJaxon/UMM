ALTER TABLE draft_runs
    ADD COLUMN IF NOT EXISTS draft_order JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS draft_trades (
    id VARCHAR(64) PRIMARY KEY,
    draft_run_id VARCHAR(64) NOT NULL REFERENCES draft_runs(id),
    trade_number INTEGER NOT NULL,
    pick_number INTEGER NOT NULL,
    acquired_pick_number INTEGER NOT NULL,
    moving_up_team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    moving_down_team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    direction VARCHAR(20) NOT NULL,
    current_pick_value NUMERIC(8, 2) NOT NULL,
    acquired_pick_value NUMERIC(8, 2) NOT NULL,
    value_delta NUMERIC(8, 2) NOT NULL,
    tendency_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_draft_trades_run ON draft_trades(draft_run_id, trade_number);