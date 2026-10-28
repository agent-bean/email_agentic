.DEFAULT_GOAL := help
APP_CONTROL := uv run --project apps/backend python scripts/app-control.py

.PHONY: help setup check db build migrate up down status test web-build lint typecheck

help: ## Show local development commands
	@awk 'BEGIN {FS = ":.*## "; print "Run from the repository root:"} /^[a-z-]+:.*## / {printf "  make %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install backend and web development dependencies
	uv sync --project apps/backend
	npm ci --prefix apps/web

check: ## Validate the local Compose configuration
	$(APP_CONTROL) check

db: ## Start the local PostgreSQL container
	$(APP_CONTROL) db

build: ## Build the separate backend and web images
	$(APP_CONTROL) build

migrate: ## Back up the database and apply migrations explicitly
	$(APP_CONTROL) migrate

up: ## Start the local stack (run build and migrate first)
	APP_ORIGIN="$${APP_ORIGIN:-http://127.0.0.1:8000}" $(APP_CONTROL) up

down: ## Stop the local stack, preserving data volumes
	$(APP_CONTROL) down

status: ## Show local container status
	$(APP_CONTROL) status

test: ## Back up and run backend tests with a separate local test database
	$(APP_CONTROL) test

web-build: ## Typecheck and build the web application locally
	npm run build --prefix apps/web

lint: ## Lint the application backend and local stack helper
	uv run --project apps/backend ruff check --config apps/backend/pyproject.toml apps/backend/src apps/backend/tests scripts/app-control.py

typecheck: ## Typecheck the web application
	npm run typecheck --prefix apps/web
