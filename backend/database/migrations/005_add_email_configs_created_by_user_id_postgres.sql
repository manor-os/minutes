-- Add created_by_user_id to email_configs (PostgreSQL)
-- Fixes: Unknown column 'email_configs.created_by_user_id' in 'field list'
-- Migration: 005_add_email_configs_created_by_user_id_postgres.sql

ALTER TABLE email_configs
ADD COLUMN IF NOT EXISTS created_by_user_id BIGINT NULL;
