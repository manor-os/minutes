"""Pytest config: make `api`, `database` importable like the app does."""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Neutralize external connections by default; individual tests override.
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db")
# The OpenAI client validates credentials during construction even when a test
# replaces its network call. Keep collection offline and let tests that cover
# missing credentials explicitly delete or override this placeholder.
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
