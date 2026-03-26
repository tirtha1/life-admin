.PHONY: help build up down logs restart shell migrate dev-token test lint fmt

# ─── Variables ────────────────────────────────────────────────────────────────
COMPOSE := docker compose
APP_SERVICE ?= api

# ─── Help ─────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Life Admin — Make targets"
	@echo ""
	@echo "  Infrastructure"
	@echo "    make build       Build all Docker images"
	@echo "    make up          Start all services (detached)"
	@echo "    make down        Stop all services"
	@echo "    make logs        Tail logs for all services"
	@echo "    make restart     Restart a service: make restart APP_SERVICE=api"
	@echo ""
	@echo "  Database"
	@echo "    make migrate     Run init.sql against local Postgres"
	@echo ""
	@echo "  Development"
	@echo "    make shell       Open a shell in the api container"
	@echo "    make dev-token   Print a dev JWT for user 00000000-0000-0000-0000-000000000001"
	@echo "    make test        Run all tests"
	@echo "    make lint        Run ruff linter"
	@echo "    make fmt         Format code with ruff"
	@echo ""

# ─── Infrastructure ───────────────────────────────────────────────────────────
build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

restart:
	$(COMPOSE) restart $(APP_SERVICE)

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	@echo "Running migrations against local Postgres..."
	docker exec -i lifeadmin-postgres psql -U lifeadmin -d lifeadmin < migrations/init.sql
	@echo "Migration complete."

# ─── Development ──────────────────────────────────────────────────────────────
shell:
	$(COMPOSE) exec $(APP_SERVICE) bash

dev-token:
	@$(COMPOSE) exec api python -c "\
from services.api.security import create_dev_token; \
print(create_dev_token('00000000-0000-0000-0000-000000000001', 'dev@lifeadmin.local'))"

# ─── Testing ──────────────────────────────────────────────────────────────────
test:
	python -m pytest tests/ -v --tb=short

test-unit:
	python -m pytest tests/unit/ -v --tb=short

test-integration:
	python -m pytest tests/integration/ -v --tb=short -m integration

# ─── Code quality ─────────────────────────────────────────────────────────────
lint:
	ruff check services/ shared/ tests/

fmt:
	ruff format services/ shared/ tests/
	ruff check --fix services/ shared/ tests/
