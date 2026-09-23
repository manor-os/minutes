.PHONY: help up down build restart logs ps shell-backend shell-db test clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start all services
	docker-compose up -d

down: ## Stop all services
	docker-compose down

build: ## Build all Docker images
	docker-compose build

rebuild: ## Rebuild and restart all services
	docker-compose up -d --build

restart: ## Restart all services
	docker-compose restart

logs: ## View logs from all services
	docker-compose logs -f

logs-backend: ## View backend logs
	docker-compose logs -f backend

logs-celery: ## View Celery worker logs
	docker-compose logs -f celery-worker

logs-db: ## View database logs
	docker-compose logs -f postgres

ps: ## Show status of all services
	docker-compose ps

shell-backend: ## Open shell in backend container
	docker-compose exec backend /bin/bash

shell-db: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U meeting_user -d meeting_notes

test: ## Test backend API
	curl http://localhost:8000/health

init-db: ## Initialize database
	docker-compose exec backend python database/migrations/init_db.py

clean: ## Remove all containers, volumes, and images
	docker-compose down -v
	docker system prune -f

clean-all: clean ## Remove everything including images
	docker-compose down -v --rmi all
	docker system prune -af

