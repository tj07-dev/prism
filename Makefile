# ================================
# Makefile for E-Commerce Recommendation System
# ================================

.DEFAULT_GOAL := help

# ================================
# Help
# ================================
.PHONY: help
help:
	@echo "E-Commerce Recommendation System - Available Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Initial setup (create .env and start services)"
	@echo ""
	@echo "Docker:"
	@echo "  make build          - Build Docker images"
	@echo "  make up             - Start all services"
	@echo "  make down           - Stop all services"
	@echo "  make restart        - Restart all services"
	@echo "  make logs           - View all logs"
	@echo "  make logs-backend   - View backend logs"
	@echo "  make logs-frontend  - View frontend logs"
	@echo "  make logs-db        - View database logs"
	@echo "  make ps             - Show running containers"
	@echo "  make clean          - Stop services and remove volumes"
	@echo ""
	@echo "Development:"
	@echo "  make shell-backend  - Shell into backend container"
	@echo "  make shell-frontend - Shell into frontend container"
	@echo "  make shell-db       - PostgreSQL CLI"
	@echo "  make pgadmin        - Start PgAdmin"
	@echo ""
	@echo "Database:"
	@echo "  make seed-data              - Seed database with sample data"
	@echo "  make seed-user-segment-data - Seed user segment data and mappings"
	@echo "  make migrate                - Run database migrations"
	@echo "  make migrate-create         - Create new migration"
	@echo "  make backup-db              - Backup database"
	@echo "  make restore-db             - Restore database"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run backend tests"
	@echo "  make test-frontend  - Run frontend tests"
	@echo "  make lint           - Run linters"
	@echo ""

# ================================
# Setup
# ================================
.PHONY: setup

setup:
	@echo "Setting up environment..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env file created. Please update it with your values."; \
	else \
		echo ".env file already exists."; \
	fi
	@echo "Starting services..."
	@docker compose up -d
	@echo ""
	@echo "Waiting for services to be ready..."
	@sleep 15
	@echo ""
	@echo "✅ Setup complete! Services are running."
	@echo ""
	@echo "Access the application:"
	@echo "  Frontend: http://localhost:3000"
	@echo "  Backend:  http://localhost:8000"
	@echo "  API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "Default admin login:"
	@echo "  Email:    admin@example.com"
	@echo "  Password: admin123"
	@echo ""
	@echo "📝 Database initialized automatically on first run!"

# ================================
# Docker Commands
# ================================
.PHONY: build up down restart logs ps clean

build:
	@echo "Building Docker images..."
	docker compose build

build-no-cache:
	@echo "Building Docker images (no cache)..."
	docker compose build --no-cache

up:
	@echo "Starting services..."
	docker compose up -d

down:
	@echo "Stopping services..."
	docker compose down

restart:
	@echo "Restarting services..."
	docker compose restart

logs:
	@echo "Showing logs..."
	docker compose logs -f

logs-backend:
	@echo "Showing backend logs..."
	docker compose logs -f backend

logs-frontend:
	@echo "Showing frontend logs..."
	docker compose logs -f frontend

logs-db:
	@echo "Showing database logs..."
	docker compose logs -f postgres

ps:
	@echo "Showing running containers..."
	docker compose ps

clean:
	@echo "Stopping services and removing volumes..."
	docker compose down -v
	@echo "Cleaning Docker system..."
	docker system prune -f

# ================================
# Development
# ================================
.PHONY: shell-backend shell-frontend shell-db

shell-backend:
	@echo "Opening shell in backend container..."
	docker compose exec backend bash

shell-frontend:
	@echo "Opening shell in frontend container..."
	docker compose exec frontend sh

shell-db:
	@echo "Opening PostgreSQL CLI..."
	docker compose exec postgres psql -U ecommerce_user -d ecommerce

# ================================
# PgAdmin
# ================================
.PHONY: pgadmin

pgadmin:
	@echo "Starting PgAdmin..."
	docker compose --profile tools up -d pgadmin
	@echo "PgAdmin available at http://localhost:5050"
	@echo "Email: admin@admin.com"
	@echo "Password: admin"

# ================================
# Database
# ================================
.PHONY: migrate migrate-create backup-db restore-db seed-data

seed-data:
	@echo "Seeding database with sample data..."
	@echo "Ensuring services are running..."
	@docker compose up -d postgres backend
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Copying seed script and data to container..."
	@docker cp scripts/seed_database.py ecommerce-backend:/tmp/seed_database.py
	@docker cp data/products-data.csv ecommerce-backend:/tmp/products-data.csv
	@echo "Running seed script..."
	@docker compose exec backend python /tmp/seed_database.py
	@echo "✅ Database seeding completed!"

seed-user-segment-data:
	@echo "Seeding user segment data..."
	@echo "Ensuring services are running..."
	@docker compose up -d postgres backend
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo "Copying user segment seed script to container..."
	@docker cp scripts/seed_user_segments.py ecommerce-backend:/tmp/seed_user_segments.py
	@echo "Running user segment seeding script..."
	@docker compose exec backend python /tmp/seed_user_segments.py
	@echo "✅ User segment data seeding completed!"

migrate:
	@echo "Running database migrations..."
	docker compose exec backend alembic upgrade head

migrate-create:
	@echo "Creating new migration..."
	@read -p "Enter migration message: " msg; \
	docker compose exec backend alembic revision --autogenerate -m "$$msg"

backup-db:
	@echo "Backing up database..."
	@mkdir -p backups
	docker compose exec -T postgres pg_dump -U ecommerce_user ecommerce > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Database backed up to backups/"

restore-db:
	@echo "Restoring database..."
	@read -p "Enter backup file path: " backup; \
	docker compose exec -T postgres psql -U ecommerce_user ecommerce < $$backup

# ================================
# Testing
# ================================
.PHONY: test test-frontend test-coverage lint

test:
	@echo "Running backend tests..."
	docker compose exec backend pytest

test-coverage:
	@echo "Running backend tests with coverage..."
	docker compose exec backend pytest --cov=app --cov-report=html

test-frontend:
	@echo "Running frontend tests..."
	docker compose exec frontend npm test

lint:
	@echo "Running linters..."
	docker compose exec backend flake8 app/
	docker compose exec backend black --check app/
	docker compose exec frontend npm run lint

# ================================
# Utility
# ================================
.PHONY: logs-tail stats volumes

logs-tail:
	@echo "Tailing logs (last 100 lines)..."
	docker compose logs --tail=100

stats:
	@echo "Docker resource usage..."
	docker stats --no-stream

volumes:
	@echo "Listing volumes..."
	docker volume ls | grep recommendationsystem
