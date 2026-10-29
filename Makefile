.DEFAULT_GOAL := help
APP_CONTROL := uv run --project apps/backend python scripts/app-control.py

.PHONY: help setup check db build migrate up down status test web-build lint typecheck release

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
	$(APP_CONTROL) test $(PYTEST_ARGS)

web-build: ## Typecheck and build the web application locally
	npm run build --prefix apps/web

lint: ## Lint the application backend and local stack helper
	uv run --project apps/backend ruff check --config apps/backend/pyproject.toml apps/backend/src apps/backend/tests scripts/app-control.py scripts/prepare-release.py scripts/check-pr-conventions.py scripts/install-git-hooks.py scripts/tests/test_delivery_workflow.py

typecheck: ## Typecheck the web application
	npm run typecheck --prefix apps/web

release: ## Package committed deployment source without credentials or runtime data
	python3 scripts/prepare-release.py

.PHONY: test-unit test-integration test-e2e test-scripts web-test hooks-install

test-unit: ## Run backend unit tests without PostgreSQL
	uv run --project apps/backend pytest apps/backend/tests/unit -q

test-integration: ## Run backend integration tests through the isolated DB helper
	$(APP_CONTROL) test -m integration $(PYTEST_ARGS)

test-e2e: ## Run backend end-to-end tests through the isolated DB helper
	$(APP_CONTROL) test -m e2e $(PYTEST_ARGS)

test-scripts: ## Check delivery and operational scripts
	uv run --project apps/backend pytest -c apps/backend/pyproject.toml scripts/tests -q

web-test: ## Run all web tests with backup and isolated test DB preparation
	npm run test:unit --prefix apps/web
	npm run test:integration --prefix apps/web
	$(APP_CONTROL) web-test

hooks-install: ## Opt in to repository hooks without replacing existing hooks
	python3 scripts/install-git-hooks.py
