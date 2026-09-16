-- Add detailed, time-versioned prospect measurements and athletic scores.
CREATE TABLE IF NOT EXISTS player_measurements (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    observed_at TIMESTAMP NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_record_id VARCHAR(150),
    age_years NUMERIC(5, 2),
    height_inches NUMERIC(5, 2),
    weight_lbs NUMERIC(6, 2),
    hand_inches NUMERIC(5, 2),
    arm_inches NUMERIC(5, 2),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS player_athletic_scores (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(64) NOT NULL REFERENCES players(id),
    observed_at TIMESTAMP NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    metric_name VARCHAR(80) NOT NULL,
    score NUMERIC(8, 3),
    score_scale VARCHAR(40),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);