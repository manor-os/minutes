-- Manor Cloud entity IDs are string ULIDs. Keep numeric local IDs compatible
-- by storing every meeting entity_id as text.
-- Migration: 011_alter_entity_id_to_text_postgres.sql

ALTER TABLE meetings
    ALTER COLUMN entity_id TYPE VARCHAR(64) USING entity_id::text,
    ALTER COLUMN entity_id SET DEFAULT '0';
