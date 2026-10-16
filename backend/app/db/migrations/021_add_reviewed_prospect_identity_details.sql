ALTER TABLE prospect_source_identities
    ADD COLUMN IF NOT EXISTS reviewed_name VARCHAR(200);
ALTER TABLE prospect_source_identities
    ADD COLUMN IF NOT EXISTS reviewed_school VARCHAR(100);
