-- Add entity_id and created_by_user_id columns to meetings table for multi-tenant isolation
-- Migration: 003_add_entity_id_and_user_id.sql

-- Add entity_id column (required for multi-tenant isolation)
ALTER TABLE meetings 
ADD COLUMN entity_id INT NOT NULL DEFAULT 0 AFTER token_cost;

-- Add created_by_user_id column (optional, tracks who recorded the meeting)
ALTER TABLE meetings 
ADD COLUMN created_by_user_id INT NULL AFTER entity_id;

-- Create index on entity_id for faster queries
CREATE INDEX idx_meetings_entity_id ON meetings(entity_id);

-- Create index on created_by_user_id for user-specific queries
CREATE INDEX idx_meetings_created_by_user_id ON meetings(created_by_user_id);
