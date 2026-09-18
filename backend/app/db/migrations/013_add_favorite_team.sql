-- Store the user's preferred NFL team for account personalization.
ALTER TABLE users ADD COLUMN IF NOT EXISTS favorite_team_id VARCHAR(64) REFERENCES teams(id);
CREATE INDEX IF NOT EXISTS ix_users_favorite_team_id ON users(favorite_team_id);