# Quick Start with Docker

Get Meeting Note Taker running in 3 minutes with Docker!

## Prerequisites

- Docker Desktop (or Docker + Docker Compose)
- OpenAI API key

## Steps

### 1. Create Environment File

```bash
cd meeting-note-taker
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```env
OPENAI_API_KEY=sk-your-actual-key-here
```

### 2. Start Everything

```bash
docker-compose up -d
```

This starts:
- ✅ PostgreSQL database
- ✅ Redis
- ✅ Backend API (port 8000)
- ✅ Celery worker
- ✅ Phone recorder (port 3001)

### 3. Verify

```bash
# Check services are running
docker-compose ps

# Test backend
curl http://localhost:8000/health

# View logs
docker-compose logs -f
```

### 4. Access Services

- **Backend API:** http://localhost:8000
- **Phone Recorder:** http://localhost:3001
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379

## Common Commands

```bash
# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart services
docker-compose restart

# Rebuild after code changes
docker-compose up -d --build

# Access backend shell
docker-compose exec backend /bin/bash

# Access database
docker-compose exec postgres psql -U meeting_user -d meeting_notes
```

## Using Make (Optional)

If you have `make` installed:

```bash
make up          # Start services
make down        # Stop services
make logs        # View logs
make ps          # Show status
make test        # Test API
make shell-backend  # Backend shell
make shell-db    # Database shell
```

## Next Steps

1. **Load Browser Extension:**
   - Update API URL to `http://localhost:8000` in extension files
   - Load in Chrome/Edge

2. **Test Phone Recorder:**
   - Open http://localhost:3001
   - Start recording

3. **Check Documentation:**
   - [DOCKER_SETUP.md](DOCKER_SETUP.md) - Full Docker guide
   - [README.md](README.md) - Complete documentation

## Troubleshooting

**Services won't start:**
```bash
docker-compose logs
```

**Port already in use:**
- Change ports in `docker-compose.yml`
- Or stop conflicting services

**Database connection errors:**
- Wait a few seconds for PostgreSQL to initialize
- Check logs: `docker-compose logs postgres`

**Need to reset everything:**
```bash
docker-compose down -v
docker-compose up -d
```

That's it! You're ready to record meetings! 🎉

