-- Store versioned baseline position importance for draft-board calculations.
CREATE TABLE IF NOT EXISTS position_importance (
    position_code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    importance_score NUMERIC(5, 2) NOT NULL,
    weighting_version VARCHAR(40) NOT NULL,
    rationale VARCHAR(500) NOT NULL
);