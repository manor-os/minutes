#!/usr/bin/env python3
"""
Initialize database with migrations
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()

def init_database():
    """Initialize database with schema"""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://meeting_user:meeting_password@localhost:5432/meeting_notes"
    )
    
    # Determine which SQL file to use
    if "postgresql" in database_url.lower():
        sql_file = Path(__file__).parent / "001_create_meetings_table_postgres.sql"
    else:
        sql_file = Path(__file__).parent / "001_create_meetings_table.sql"
    
    if not sql_file.exists():
        print(f"SQL file not found: {sql_file}")
        return False
    
    try:
        engine = create_engine(database_url)
        
        # Read and execute SQL file
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        with engine.connect() as conn:
            # For PostgreSQL, execute the entire SQL file at once
            # This properly handles functions with dollar-quoted strings
            if "postgresql" in database_url.lower():
                try:
                    # Use raw connection for executing multiple statements
                    raw_conn = conn.connection
                    with raw_conn.cursor() as cursor:
                        cursor.execute(sql_content)
                        raw_conn.commit()
                    print(f"✓ SQL file executed successfully")
                except Exception as e:
                    error_msg = str(e).lower()
                    # Ignore "already exists" errors
                    if "already exists" not in error_msg and "duplicate" not in error_msg:
                        print(f"Warning: {e}")
            else:
                # For MySQL/SQLite, split by semicolon
                for statement in sql_content.split(';'):
                    statement = statement.strip()
                    if statement and not statement.startswith('--'):
                        try:
                            conn.execute(text(statement))
                            conn.commit()
                        except Exception as e:
                            # Ignore "already exists" errors
                            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                                print(f"Warning: {e}")
        
        print(f"✓ Database initialized successfully using {sql_file.name}")
        
        # Run additional migrations if needed
        migrations = []
        if "postgresql" in database_url.lower():
            migrations = [
                "002_add_token_cost_column.sql",
                "003_add_entity_id_and_user_id_postgres.sql",
                "004_add_uploading_status_postgres.sql",
                "005_add_email_configs_created_by_user_id_postgres.sql",
                "006_add_tags_favorite.sql",
                "007_add_share_token.sql",
                "008_add_webhook_url.sql",
                "009_alter_created_by_user_id_to_text_postgres.sql",
            ]
        else:
            migrations = [
                "002_add_token_cost_column.sql",
                "003_add_entity_id_and_user_id.sql",
                "004_add_uploading_status.sql",
                "005_add_email_configs_created_by_user_id.sql",
                "006_add_tags_favorite.sql",
                "007_add_share_token.sql",
                "008_add_webhook_url.sql",
            ]
        
        for migration_name in migrations:
            migration_file = Path(__file__).parent / migration_name
            if migration_file.exists():
                try:
                    with open(migration_file, 'r') as f:
                        migration_sql = f.read()
                    with engine.connect() as conn:
                        raw_conn = conn.connection
                        with raw_conn.cursor() as cursor:
                            cursor.execute(migration_sql)
                            raw_conn.commit()
                        print(f"✓ Migration {migration_file.name} executed successfully")
                except Exception as e:
                    error_msg = str(e).lower()
                    # Ignore "already exists" errors, constraint errors, and "does not exist" errors (for DROP)
                    if ("already exists" not in error_msg and 
                        "duplicate" not in error_msg and 
                        "column" not in error_msg and
                        "constraint" not in error_msg and
                        "does not exist" not in error_msg):
                        print(f"Warning: Migration {migration_file.name} - {e}")
                    else:
                        print(f"✓ Migration {migration_file.name} already applied or safe to skip")
        
        return True
        
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False

if __name__ == "__main__":
    init_database()

