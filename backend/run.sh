#!/bin/bash

# Meeting Note Taker - Backend Startup Script

echo "Starting Meeting Note Taker Backend..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env file from example..."
    cp .env.example .env
    echo "Please update .env with your configuration!"
    exit 1
fi

# Initialize database
echo "Initializing database..."
python -c "from database.db import init_db; init_db()"

# Start FastAPI server
echo "Starting FastAPI server on http://localhost:8000"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

