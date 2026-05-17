-- Add entity_id and created_by_user_id columns to meetings table for multi-tenant isolation (PostgreSQL)
-- Migration: 003_add_entity_id_and_user_id_postgres.sql

-- Add entity_id column (required for multi-tenant isolation)
ALTER TABLE meetings 
ADD COLUMN IF NOT EXISTS entity_id INTEGER NOT NULL DEFAULT 0;

-- Add created_by_user_id column (optional, tracks who recorded the meeting)
ALTER TABLE meetings 
ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER NULL;

-- Create index on entity_id for faster queries
CREATE INDEX IF NOT EXISTS idx_meetings_entity_id ON meetings(entity_id);

-- Create index on created_by_user_id for user-specific queries
CREATE INDEX IF NOT EXISTS idx_meetings_created_by_user_id ON meetings(created_by_user_id);
