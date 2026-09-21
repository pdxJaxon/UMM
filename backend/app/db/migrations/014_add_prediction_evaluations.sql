-- Persist historical board accuracy scorecards for defensible product metrics.
CREATE TABLE IF NOT EXISTS prediction_evaluations (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(64) NOT NULL REFERENCES teams(id),
    board_id INTEGER REFERENCES team_boards(id),
    draft_year INTEGER NOT NULL,
    evaluation_scope VARCHAR(40) NOT NULL DEFAULT 'first_round',
    scoring_version VARCHAR(50) NOT NULL,
    evaluated_picks INTEGER NOT NULL,
    exact_hits INTEGER NOT NULL,
    player_hits INTEGER NOT NULL,
    exact_pick_rate NUMERIC(5, 2) NOT NULL,
    player_hit_rate NUMERIC(5, 2) NOT NULL,
    mean_absolute_pick_error NUMERIC(8, 2),
    evaluated_at TIMESTAMP NOT NULL,
    source_name VARCHAR(100) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_prediction_evaluations_lookup
    ON prediction_evaluations(team_id, draft_year, evaluated_at);