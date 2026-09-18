-- Change created_by_user_id in meetings from INTEGER to TEXT to support UUID user IDs (PostgreSQL)
ALTER TABLE meetings ALTER COLUMN created_by_user_id TYPE TEXT USING created_by_user_id::TEXT;
