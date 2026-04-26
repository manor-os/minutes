"""
Standalone local authentication - no external dependencies.
Users stored in the app's own PostgreSQL database.
"""
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import bcrypt
import jwt
from loguru import logger

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/meeting_notes")

# Default admin credentials for community edition (configurable via env vars)
DEFAULT_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@minutes.local")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

JWT_SECRET = os.getenv("JWT_SECRET", "meeting-note-taker-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = int(os.getenv("TOKEN_EXPIRY_HOURS", "72"))


def _get_db_connection():
    """Get psycopg2 connection."""
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_users_table():
    """Create users table if not exists."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    stt_api_key VARCHAR(512),
                    llm_api_key VARCHAR(512),
                    llm_model VARCHAR(100),
                    llm_base_url VARCHAR(255)
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
                -- Ensure new columns exist on older tables
                ALTER TABLE users ADD COLUMN IF NOT EXISTS stt_api_key VARCHAR(512);
                ALTER TABLE users ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500);
            """)
            conn.commit()
            logger.info("Users table initialized")
    except Exception as e:
        logger.error(f"Failed to init users table: {e}")
        conn.rollback()
    finally:
        conn.close()


def register_user(email: str, password: str, name: str = "") -> Optional[Dict[str, Any]]:
    """Register a new user. Returns user info or None if email already exists."""
    # Ensure the users table exists in case init failed at startup (e.g. DB not ready)
    init_users_table()
    conn = _get_db_connection()
    try:
        # Hash password
        pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash, name) VALUES (%s, %s, %s) RETURNING id, email, name, created_at",
                (email.lower().strip(), pw_hash, name or email.split("@")[0])
            )
            user = cur.fetchone()
            conn.commit()
            return dict(user) if user else None
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            logger.warning(f"Email already registered: {email}")
            return None
        logger.error(f"Registration error: {e}")
        return None
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Validate email + password. Returns user info or None."""
    init_users_table()
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, password_hash, name, stt_api_key, llm_api_key, llm_model, llm_base_url, webhook_url FROM users WHERE email = %s", (email.lower().strip(),))
            user = cur.fetchone()
            if not user:
                return None
            if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
                return None
            return {"id": str(user["id"]), "email": user["email"], "name": user["name"],
                    "stt_api_key": user.get("stt_api_key"),
                    "llm_api_key": user.get("llm_api_key"), "llm_model": user.get("llm_model"),
                    "llm_base_url": user.get("llm_base_url")}
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None
    finally:
        conn.close()


def _stable_entity_id(email: str) -> int:
    """Generate a stable numeric entity_id from email (for local mode).
    Must fit in PostgreSQL INTEGER (max 2,147,483,647)."""
    import hashlib
    h = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    return int(h[:7], 16) % 2000000000


def generate_token(user_info: Dict[str, Any]) -> str:
    """Generate JWT token with entity_id for local auth compatibility."""
    email = user_info.get("email", "")
    payload = {
        "sub": user_info.get("id") or email,
        "email": email,
        "name": user_info.get("name", ""),
        "entity_id": _stable_entity_id(email),
        "user_id": user_info.get("id") or user_info.get("email"),
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, name, stt_api_key, llm_api_key, llm_model, llm_base_url, webhook_url FROM users WHERE email = %s", (email.lower().strip(),))
            user = cur.fetchone()
            return dict(user) if user else None
    except Exception as e:
        logger.error(f"Get user error: {e}")
        return None
    finally:
        conn.close()


def change_password(email: str, current_password: str, new_password: str) -> dict:
    """Change user password (requires current password verification)."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE email = %s", (email.lower().strip(),))
            user = cur.fetchone()
            if not user:
                return {"success": False, "error": "User not found"}
            if not bcrypt.checkpw(current_password.encode("utf-8"), user["password_hash"].encode("utf-8")):
                return {"success": False, "error": "Current password is incorrect"}
            new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cur.execute(
                "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE email = %s",
                (new_hash, email.lower().strip())
            )
            conn.commit()
            return {"success": True}
    except Exception as e:
        conn.rollback()
        logger.error(f"Change password error: {e}")
        return {"success": False, "error": "Failed to change password"}
    finally:
        conn.close()


def delete_account(email: str, password: str) -> dict:
    """Delete user account and all their meetings."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verify password first
            cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email.lower().strip(),))
            user = cur.fetchone()
            if not user:
                return {"success": False, "error": "User not found"}
            if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
                return {"success": False, "error": "Password is incorrect"}
            # Delete all meetings for this user's entity_id
            entity_id = _stable_entity_id(email)
            cur.execute("DELETE FROM meetings WHERE entity_id = %s", (entity_id,))
            # Delete the user record
            cur.execute("DELETE FROM users WHERE email = %s", (email.lower().strip(),))
            conn.commit()
            logger.info(f"Account deleted: {email}")
            return {"success": True}
    except Exception as e:
        conn.rollback()
        logger.error(f"Delete account error: {e}")
        return {"success": False, "error": "Failed to delete account"}
    finally:
        conn.close()


def seed_default_admin() -> bool:
    """Create the default admin account if it does not exist yet.

    Idempotent — safe to call on every startup.
    Credentials are controlled by ADMIN_EMAIL / ADMIN_PASSWORD env vars.
    """
    if get_user_by_email(DEFAULT_ADMIN_EMAIL):
        return False  # already seeded
    result = register_user(DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, "Admin")
    if result:
        logger.info(f"Default admin account created: {DEFAULT_ADMIN_EMAIL}")
        return True
    logger.warning("Failed to create default admin account")
    return False


def get_user_webhook_url(email: str) -> Optional[str]:
    """Get webhook URL for a user by email."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT webhook_url FROM users WHERE email = %s", (email.lower().strip(),))
            row = cur.fetchone()
            return row["webhook_url"] if row else None
    except Exception as e:
        logger.debug(f"Get webhook URL error: {e}")
        return None
    finally:
        conn.close()


def update_user_webhook_url(email: str, webhook_url: Optional[str]) -> bool:
    """Update webhook URL for a user."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET webhook_url = %s, updated_at = NOW() WHERE email = %s",
                (webhook_url or None, email.lower().strip())
            )
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Update webhook URL error: {e}")
        return False
    finally:
        conn.close()


def get_webhook_url_by_entity_id(entity_id: int) -> Optional[str]:
    """Get webhook URL by entity_id (for celery tasks)."""
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            # entity_id is derived from email hash, so we need to check all users
            # In local mode each user has a unique entity_id
            cur.execute("SELECT email, webhook_url FROM users WHERE webhook_url IS NOT NULL")
            for row in cur.fetchall():
                if _stable_entity_id(row["email"]) == entity_id:
                    return row["webhook_url"]
            return None
    except Exception as e:
        logger.debug(f"Get webhook by entity_id error: {e}")
        return None
    finally:
        conn.close()


def update_user_llm_config(email: str, stt_api_key: str = None, llm_api_key: str = None, llm_model: str = None, llm_base_url: str = None) -> bool:
    """Update user's AI configuration (STT + LLM)."""
    conn = _get_db_connection()
    try:
        sets = []
        vals = []
        if stt_api_key is not None:
            sets.append("stt_api_key = %s")
            vals.append(stt_api_key)
        if llm_api_key is not None:
            sets.append("llm_api_key = %s")
            vals.append(llm_api_key)
        if llm_model is not None:
            sets.append("llm_model = %s")
            vals.append(llm_model)
        if llm_base_url is not None:
            sets.append("llm_base_url = %s")
            vals.append(llm_base_url)
        if not sets:
            return True
        sets.append("updated_at = NOW()")
        vals.append(email.lower().strip())
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE email = %s", vals)
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Update LLM config error: {e}")
        return False
    finally:
        conn.close()
