-- Track which auth path created the meeting so the async worker bills correctly.
-- "manor" → Manor-SSO-backed user (Manor OR Google login; Google is normalized
--            to "manor" at stamp time): charge entity credit on the shared key.
-- "local" → BYO-key user, run on their own key, no Manor billing.
-- Migration: 010_add_auth_source.sql

ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS auth_source VARCHAR(16) NOT NULL DEFAULT 'local';
