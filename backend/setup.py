#!/usr/bin/env python3
"""
Setup script for Meeting Note Taker backend
"""
import os
import sys
from pathlib import Path

def create_env_file():
    """Create .env file from example if it doesn't exist"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print("✓ .env file already exists")
        return
    
    if env_example.exists():
        import shutil
        shutil.copy(env_example, env_file)
        print("✓ Created .env file from .env.example")
        print("⚠ Please update .env with your configuration!")
    else:
        # Create basic .env file
        env_content = """# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/meeting_notes

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Application Configuration
DEBUG=True
LOG_LEVEL=INFO

# Storage Configuration
STORAGE_DIR=./storage/meetings
"""
        with open(env_file, "w") as f:
            f.write(env_content)
        print("✓ Created .env file")
        print("⚠ Please update .env with your configuration!")


def create_storage_dirs():
    """Create storage directories"""
    storage_dir = Path("storage/meetings")
    storage_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created storage directory: {storage_dir}")


def init_database():
    """Initialize database tables"""
    try:
        from database.db import init_db
        init_db()
        print("✓ Database initialized")
    except Exception as e:
        print(f"⚠ Database initialization failed: {e}")
        print("  Make sure your database is running and DATABASE_URL is correct")


def main():
    """Run setup"""
    print("Setting up Meeting Note Taker backend...\n")
    
    # Change to script directory
    os.chdir(Path(__file__).parent)
    
    create_env_file()
    create_storage_dirs()
    init_database()
    
    print("\n✓ Setup complete!")
    print("\nNext steps:")
    print("1. Update .env with your configuration")
    print("2. Install dependencies: pip install -r requirements.txt")
    print("3. Start server: uvicorn api.main:app --reload")
    print("4. Start Celery worker: celery -A celery_tasks worker --loglevel=info")


if __name__ == "__main__":
    main()

