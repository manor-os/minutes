-- Add 'uploading' status to meetings table check constraint (PostgreSQL)
-- Migration: 004_add_uploading_status_postgres.sql

-- Drop the existing check constraint
ALTER TABLE meetings DROP CONSTRAINT IF EXISTS meetings_status_check;

-- Add new check constraint that includes 'uploading' status
ALTER TABLE meetings ADD CONSTRAINT meetings_status_check 
    CHECK (status IN ('uploading', 'processing', 'completed', 'failed'));
