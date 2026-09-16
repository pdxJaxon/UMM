-- Add display metadata to an existing teams table before running the seed command.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS logo_url VARCHAR(500);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS helmet_url VARCHAR(500);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS official_url VARCHAR(500);