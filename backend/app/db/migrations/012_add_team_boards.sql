-- Store versioned team-specific default and user-customized boards.
CREATE TABLE IF NOT EXISTS team_boards (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    user_id VARCHAR(64) REFERENCES users(id),
    draft_year INTEGER NOT NULL,
    board_type VARCHAR(20) NOT NULL DEFAULT 'default',
    version INTEGER NOT NULL DEFAULT 1,
    generated_at TIMESTAMP NOT NULL,
    scoring_version VARCHAR(50) NOT NULL,
    scoring_weights JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS team_board_entries (
    id SERIAL PRIMARY KEY,
    board_id INTEGER NOT NULL REFERENCES team_boards(id) ON DELETE CASCADE,
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    rank_position INTEGER NOT NULL,
    score NUMERIC(8, 3) NOT NULL,
    score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_team_board_player UNIQUE (board_id, player_id)
);