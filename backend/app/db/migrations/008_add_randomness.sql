-- Store team defaults, per-draft overrides, and per-pick audit values.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS randomness_score NUMERIC(5, 2) NOT NULL DEFAULT 50;
ALTER TABLE draft_runs ADD COLUMN IF NOT EXISTS randomness_overrides JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE draft_picks ADD COLUMN IF NOT EXISTS randomness_factor NUMERIC(5, 2) NOT NULL DEFAULT 0;