ALTER TABLE meetings ADD COLUMN IF NOT EXISTS share_token VARCHAR(64) DEFAULT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_meetings_share_token ON meetings(share_token) WHERE share_token IS NOT NULL;
