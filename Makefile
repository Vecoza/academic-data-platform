.PHONY: help install up down logs psql check-db lint format test clean

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

lint:  ## Run linter
	ruff check .

format:  ## Format code
	ruff format .

test:  ## Run tests
	pytest

clean:  ## Remove caches
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
