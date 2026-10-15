CREATE TABLE IF NOT EXISTS prospect_source_identities (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    source_key VARCHAR(160) NOT NULL,
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    source_record_id VARCHAR(150),
    CONSTRAINT uq_prospect_source_identity UNIQUE (source_name, source_key)
);
CREATE INDEX IF NOT EXISTS ix_prospect_source_identities_player_id
    ON prospect_source_identities(player_id);

CREATE TABLE IF NOT EXISTS prospect_board_snapshots (
    id VARCHAR(64) PRIMARY KEY,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    source_name VARCHAR(100) NOT NULL,
    source_url VARCHAR(500) NOT NULL,
    draft_year INTEGER NOT NULL,
    collected_at TIMESTAMP NOT NULL,
    source_updated_at_display VARCHAR(200),
    collection_method VARCHAR(200) NOT NULL,
    scope TEXT NOT NULL,
    prospect_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_prospect_board_snapshots_draft_year
    ON prospect_board_snapshots(draft_year);

CREATE TABLE IF NOT EXISTS prospect_board_rankings (
    id SERIAL PRIMARY KEY,
    snapshot_id VARCHAR(64) NOT NULL REFERENCES prospect_board_snapshots(id),
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    overall_rank INTEGER NOT NULL,
    pff_grade NUMERIC(5, 2),
    source_name_display VARCHAR(200) NOT NULL,
    source_position VARCHAR(20) NOT NULL,
    source_school VARCHAR(150) NOT NULL,
    canonical_position VARCHAR(20) NOT NULL,
    college_id VARCHAR(100) NOT NULL REFERENCES colleges(id),
    CONSTRAINT uq_prospect_snapshot_player UNIQUE (snapshot_id, player_id),
    CONSTRAINT uq_prospect_snapshot_rank UNIQUE (snapshot_id, overall_rank)
);
CREATE INDEX IF NOT EXISTS ix_prospect_board_rankings_snapshot_id
    ON prospect_board_rankings(snapshot_id);
CREATE INDEX IF NOT EXISTS ix_prospect_board_rankings_player_id
    ON prospect_board_rankings(player_id);
