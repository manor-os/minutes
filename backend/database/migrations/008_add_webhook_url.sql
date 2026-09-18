-- Add webhook_url column to users table for notification webhooks
ALTER TABLE users ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500) DEFAULT NULL;
