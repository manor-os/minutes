-- Manor Cloud entity IDs are string ULIDs. Keep numeric local IDs compatible
-- by storing every meeting entity_id as text.
-- Migration: 011_alter_entity_id_to_text.sql

ALTER TABLE meetings
    MODIFY COLUMN entity_id VARCHAR(64) NOT NULL DEFAULT '0';
