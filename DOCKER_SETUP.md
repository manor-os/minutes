# Docker Setup Guide

This guide will help you set up and run the Meeting Note Taker project using Docker Compose with PostgreSQL.

## Prerequisites

- Docker Desktop installed (or Docker + Docker Compose)
- OpenAI API key

## Quick Start

### 1. Clone and Navigate

```bash
cd meeting-note-taker
```

### 2. Create Environment File

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```env
OPENAI_API_KEY=sk-your-actual-key-here
```

### 3. Start All Services

```bash
docker-compose up -d
```

This will start:
- PostgreSQL database (port 5432)
- Redis (port 6379)
- Backend API (port 8000)
- Celery worker
- Phone recorder frontend (port 3001)

### 4. Check Services

```bash
# View logs
docker-compose logs -f

# Check service status
docker-compose ps

# Test backend
curl http://localhost:8000/health
```

### 5. Stop Services

```bash
docker-compose down
```

To also remove volumes (database data):
```bash
docker-compose down -v
```

## Services

### PostgreSQL Database
- **Port:** 5432
- **User:** meeting_user
- **Password:** meeting_password
- **Database:** meeting_notes
- **Connection:** `postgresql://meeting_user:meeting_password@localhost:5432/meeting_notes`

### Redis
- **Port:** 6379
- Used for Celery task queue

### Backend API
- **Port:** 8000
- **URL:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs (if enabled)

### Celery Worker
- Processes audio transcription and summarization
- No exposed ports

### Phone Recorder
- **Port:** 3001
- **URL:** http://localhost:3001

## Development Mode

For development with hot-reload:

1. Create `docker-compose.override.yml`:
```bash
cp docker-compose.override.yml.example docker-compose.override.yml
```

2. Start services:
```bash
docker-compose up
```

The override file mounts local code directories for live updates.

## Database Management

### Access PostgreSQL

```bash
# Using docker exec
docker-compose exec postgres psql -U meeting_user -d meeting_notes

# Or using psql client
psql -h localhost -U meeting_user -d meeting_notes
```

### Run Migrations

Migrations run automatically on backend startup. To run manually:

```bash
docker-compose exec backend python database/migrations/init_db.py
```

### Backup Database

```bash
docker-compose exec postgres pg_dump -U meeting_user meeting_notes > backup.sql
```

### Restore Database

```bash
docker-compose exec -T postgres psql -U meeting_user meeting_notes < backup.sql
```

## Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f celery-worker
docker-compose logs -f postgres
```

## Troubleshooting

### Services won't start

1. Check if ports are available:
```bash
# Check port 8000
lsof -i :8000

# Check port 5432
lsof -i :5432
```

2. Check Docker logs:
```bash
docker-compose logs
```

### Database connection errors

1. Wait for PostgreSQL to be ready:
```bash
docker-compose exec postgres pg_isready -U meeting_user
```

2. Check database is running:
```bash
docker-compose ps postgres
```

### Backend errors

1. Check environment variables:
```bash
docker-compose exec backend env | grep -E "DATABASE|OPENAI|CELERY"
```

2. Check backend logs:
```bash
docker-compose logs backend
```

### Celery not processing tasks

1. Check Celery worker logs:
```bash
docker-compose logs celery-worker
```

2. Verify Redis connection:
```bash
docker-compose exec redis redis-cli ping
```

## Rebuilding Images

After code changes, rebuild:

```bash
# Rebuild all services
docker-compose build

# Rebuild specific service
docker-compose build backend

# Rebuild and restart
docker-compose up -d --build
```

## Production Deployment

For production:

1. Update `docker-compose.yml`:
   - Remove development volumes
   - Set `DEBUG=False`
   - Use environment secrets
   - Configure proper CORS origins

2. Use production Dockerfile:
   - Multi-stage builds
   - Optimized images
   - Security hardening

3. Set up reverse proxy (Nginx):
   - SSL/HTTPS
   - Load balancing
   - Static file serving

## Environment Variables

Key environment variables (set in `.env`):

- `OPENAI_API_KEY` - Required for AI features
- `DATABASE_URL` - PostgreSQL connection string
- `CELERY_BROKER_URL` - Redis connection for Celery
- `CELERY_RESULT_BACKEND` - Redis connection for results
- `DEBUG` - Enable debug mode (True/False)
- `LOG_LEVEL` - Logging level (INFO, DEBUG, etc.)

## Volumes

Docker Compose creates persistent volumes:

- `postgres_data` - Database data
- `redis_data` - Redis data
- `meeting_storage` - Audio file storage

## Network

All services are on the `meeting-network` bridge network and can communicate using service names:
- `postgres` - Database hostname
- `redis` - Redis hostname
- `backend` - Backend API hostname

## Health Checks

Services include health checks:
- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`

Backend and Celery wait for dependencies to be healthy before starting.

## Next Steps

1. **Test the API:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Load browser extension:**
   - Update API URL to `http://localhost:8000`
   - Load in Chrome/Edge

3. **Access phone recorder:**
   - Open http://localhost:3001

4. **View API documentation:**
   - If enabled: http://localhost:8000/docs

## Cleanup

Remove everything:
```bash
docker-compose down -v
docker system prune -a
```

