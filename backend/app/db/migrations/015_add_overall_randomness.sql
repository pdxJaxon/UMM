-- Store the user-selected randomness baseline for each draft run.
ALTER TABLE draft_runs ADD COLUMN IF NOT EXISTS overall_randomness NUMERIC(5, 2) NOT NULL DEFAULT 50;