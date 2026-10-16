CREATE TABLE league_data_refreshes (
    id VARCHAR(64) PRIMARY KEY,
    draft_year INTEGER NOT NULL,
    reviewed_on TIMESTAMP NOT NULL,
    applied_at TIMESTAMP NOT NULL,
    prospect_snapshot_id VARCHAR(64) NOT NULL REFERENCES prospect_board_snapshots(id),
    manifest JSON NOT NULL
);
CREATE INDEX ix_league_data_refreshes_draft_year ON league_data_refreshes(draft_year);

ALTER TABLE draft_runs
    ADD COLUMN order_basis VARCHAR(40) NOT NULL DEFAULT 'legacy-unreviewed';
