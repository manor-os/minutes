-- Add created_by_user_id to email_configs (MySQL)
-- Fixes: Unknown column 'email_configs.created_by_user_id' in 'field list'
-- Migration: 005_add_email_configs_created_by_user_id.sql

ALTER TABLE email_configs
ADD COLUMN created_by_user_id BIGINT NULL COMMENT 'User who created this email config' AFTER entity_id;
