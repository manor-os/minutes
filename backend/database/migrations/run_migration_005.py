#!/usr/bin/env python3
"""
Run migration 005 to add created_by_user_id to email_configs table.
Run only if your database has the email_configs table (e.g. shared with manor-ai).
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

load_dotenv()


def run_migration_005():
    """Run migration 005: add created_by_user_id to email_configs."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://meeting_user:meeting_password@localhost:5432/meeting_notes",
    )

    # Determine which SQL file to use
    if "postgresql" in database_url.lower():
        migration_file = Path(__file__).parent / "005_add_email_configs_created_by_user_id_postgres.sql"
    else:
        migration_file = Path(__file__).parent / "005_add_email_configs_created_by_user_id.sql"

    if not migration_file.exists():
        print(f"✗ Migration file not found: {migration_file}")
        return False

    try:
        engine = create_engine(database_url)

        with open(migration_file, "r") as f:
            migration_sql = f.read()

        with engine.connect() as conn:
            if "postgresql" in database_url.lower():
                try:
                    raw_conn = conn.connection
                    with raw_conn.cursor() as cursor:
                        cursor.execute(migration_sql)
                        raw_conn.commit()
                    print(f"✓ Migration {migration_file.name} executed successfully")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "duplicate" in error_msg:
                        print("✓ Column already exists, migration already applied")
                        return True
                    if "does not exist" in error_msg:
                        print("⊘ Table email_configs not in this database, skipping")
                        return True
                    print(f"✗ Migration failed: {e}")
                    return False
            else:
                for statement in migration_sql.split(";"):
                    statement = statement.strip()
                    if statement and not statement.startswith("--"):
                        try:
                            conn.execute(text(statement))
                            conn.commit()
                        except Exception as e:
                            error_msg = str(e).lower()
                            if "already exists" in error_msg or "duplicate" in error_msg:
                                print("✓ Column already exists, migration already applied")
                                continue
                            if "doesn't exist" in error_msg or "unknown table" in error_msg:
                                print("⊘ Table email_configs not in this database, skipping")
                                return True
                            print(f"Warning: {e}")

        print("✓ Migration 005 completed successfully")
        return True

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_migration_005()
    sys.exit(0 if success else 1)
