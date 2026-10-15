-- Preserve model provenance or explicit fallback metadata for every pick.
ALTER TABLE draft_picks ADD COLUMN IF NOT EXISTS prediction_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;