-include .env
export

SEED ?= 42
STUDENTS ?= 15000
YEARS ?= 8
DAYS ?= 1

.PHONY: help install up down logs psql check-db migrate migrate-down migrate-status generate \
	generate-daily ingest ingest-full dbt-build dbt-docs quality pipeline lint format test test-unit test-db clean

help:  ## Show available commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {n++; name[n] = $$1; desc[n] = $$2; \
		if (length($$1) > width) width = length($$1)} \
		END {for (i = 1; i <= n; i++) printf "  \033[36m%-" width "s\033[0m  %s\n", name[i], desc[i]}' \
		$(MAKEFILE_LIST)

install:  ## Install the package with dev dependencies
	pip install -e ".[dev]"

up:  ## Start PostgreSQL
	docker compose up -d

down:  ## Stop containers
	docker compose down

logs:  ## Follow container logs
	docker compose logs -f

psql:  ## Open a psql shell in the database container
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

check-db:  ## Verify the database connection from Python
	python -m academic_platform.db

migrate:  ## Apply all database migrations
	alembic upgrade head

migrate-down:  ## Revert all database migrations
	alembic downgrade base

migrate-status:  ## Show the current migration and the history
	alembic current
	alembic history

generate:  ## Replace all operational data with a full generated history (SEED, STUDENTS, YEARS)
	python -m generator --mode full --seed $(SEED) --students $(STUDENTS) --years $(YEARS)

generate-daily:  ## Simulate the next days of activity after the history (DAYS, default 1)
	python -m generator --mode daily --days $(DAYS)

ingest:  ## Load new and changed operational rows into warehouse.raw
	python -m ingestion --mode incremental

ingest-full:  ## Reload every operational row into warehouse.raw (initial load, recovery)
	python -m ingestion --mode full

DBT = dbt --no-use-colors
DBT_DIRS = --project-dir dbt --profiles-dir dbt

dbt-build:  ## Build and test the warehouse models
	$(DBT) build $(DBT_DIRS)

dbt-docs:  ## Generate the dbt documentation site in dbt/target
	$(DBT) docs generate $(DBT_DIRS)

quality:  ## Reconcile row counts across layers and check raw freshness
	python -m quality
	$(DBT) source freshness $(DBT_DIRS)

pipeline: migrate generate ingest-full dbt-build quality  ## Run the whole chain on a fresh history

lint:  ## Run linter
	ruff check .

format:  ## Format code
	ruff format .

test:  ## Run all tests (database tests are skipped if PostgreSQL is not running)
	pytest

test-unit:  ## Run tests that do not need a database
	pytest -m "not db"

test-db:  ## Run database tests
	pytest -m db

clean:  ## Remove caches
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
