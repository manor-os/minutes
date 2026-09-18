-- Migration: Add token_cost column to meetings table
-- This migration adds a JSONB column to track token usage and costs for each meeting

-- For PostgreSQL
ALTER TABLE meetings 
ADD COLUMN IF NOT EXISTS token_cost JSONB;

-- For MySQL/SQLite (if needed)
-- ALTER TABLE meetings 
-- ADD COLUMN token_cost JSON;

