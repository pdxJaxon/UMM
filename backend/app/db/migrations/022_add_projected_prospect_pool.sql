ALTER TABLE prospect_board_snapshots
    ADD COLUMN projected_pool_approved_at TIMESTAMP;

ALTER TABLE draft_runs
    ADD COLUMN prospect_snapshot_id VARCHAR(64)
    REFERENCES prospect_board_snapshots(id);
