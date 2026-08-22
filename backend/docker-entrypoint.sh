#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
while ! pg_isready -h postgres -U meeting_user -d meeting_notes > /dev/null 2>&1; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done

echo "PostgreSQL is up - executing command"

# Initialize database
echo "Initializing database..."
python database/migrations/init_db.py

# Execute the main command
exec "$@"

