#!/bin/bash

# Start Celery worker for Meeting Note Taker

echo "Starting Celery worker..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start Celery worker
celery -A celery_tasks worker --loglevel=info --concurrency=2

