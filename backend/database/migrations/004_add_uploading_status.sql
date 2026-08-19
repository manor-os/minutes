-- Add 'uploading' status to meetings table ENUM (MySQL)
-- Migration: 004_add_uploading_status.sql

-- Note: MySQL ENUM modification requires ALTER TABLE with MODIFY COLUMN
-- This will add 'uploading' as the first value in the ENUM
ALTER TABLE meetings 
    MODIFY COLUMN status ENUM('uploading', 'processing', 'completed', 'failed') 
    DEFAULT 'uploading';
