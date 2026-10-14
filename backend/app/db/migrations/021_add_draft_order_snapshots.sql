CREATE TABLE IF NOT EXISTS draft_order_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    draft_year INTEGER NOT NULL,
    collected_at TIMESTAMP NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    scope VARCHAR(20) NOT NULL,
    expected_round_counts JSON NOT NULL,
    picks JSON NOT NULL,
    approved_at TIMESTAMP,
    approved_by VARCHAR(150)
);
CREATE INDEX IF NOT EXISTS ix_draft_order_snapshots_draft_year ON draft_order_snapshots (draft_year);
ALTER TABLE draft_runs ADD COLUMN IF NOT EXISTS order_provenance JSON NOT NULL DEFAULT '{}';
