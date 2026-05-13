.PHONY: dev db-up db-down install test lint typecheck check migrate

# One-command dev: install deps, start DB, migrate, runserver
dev: install db-up migrate
	python manage.py runserver 0.0.0.0:8000

# Python dependencies
install:
	pip install -e ".[dev]"

# Database
db-up:
	docker compose up -d db redis 2>/dev/null || true

db-down:
	docker compose down

# Migrations
migrate:
	python manage.py migrate

makemigrations:
	python manage.py makemigrations

# Testing
test:
	pytest -n auto

test-cov:
	pytest -n auto --cov=. --cov-report=term-missing

# Lint & Type
lint:
	ruff check .

typecheck:
	mypy .

# Contract validation
contract:
	python scripts/validate_contracts.py

# Full check
check: lint typecheck test

# Shell
shell:
	python manage.py shell_plus

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
