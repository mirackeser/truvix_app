.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
ALEMBIC := $(VENV)/bin/alembic

HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help
help: ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	python3 -m venv $(VENV)

.PHONY: install
install: $(VENV)/bin/python ## Create the virtualenv and install all dependencies
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(MAKE) unhide-venv

.PHONY: unhide-venv
unhide-venv: ## Clear the macOS hidden flag that makes Python ignore .pth files
	@if [[ "$$(uname)" == "Darwin" ]]; then \
		chflags -R nohidden $(VENV); \
		echo "Cleared UF_HIDDEN on $(VENV)"; \
	fi

.PHONY: env
env: ## Create a local .env from the template with a generated signing key
	@if [[ -f .env ]]; then \
		echo ".env already exists; leaving it untouched."; \
	else \
		key=$$($(PYTHON) -c 'import secrets; print(secrets.token_urlsafe(32))'); \
		sed -e "s|^TRUVIX_SECURITY_SECRET_KEY=$$|TRUVIX_SECURITY_SECRET_KEY=$$key|" \
			.env.example > .env; \
		echo "Wrote .env with a freshly generated signing key."; \
	fi

.PHONY: run
run: ## Start the API with auto-reload
	$(UVICORN) truvix.main:app --host $(HOST) --port $(PORT) --reload

.PHONY: lint
lint: ## Check formatting and lint rules
	$(RUFF) format --check src tests
	$(RUFF) check src tests

.PHONY: format
format: ## Apply formatting and autofixable lint rules
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

.PHONY: typecheck
typecheck: ## Run static type checking
	$(MYPY)

.PHONY: test
test: ## Run the test suite
	$(PYTEST)

.PHONY: coverage
coverage: ## Run the test suite with a coverage report
	$(PYTEST) --cov --cov-report=term-missing

.PHONY: check
check: lint typecheck test ## Run every quality gate, as CI does

.PHONY: migrate
migrate: ## Apply all pending database migrations
	$(ALEMBIC) upgrade head

.PHONY: downgrade
downgrade: ## Roll back the most recent migration
	$(ALEMBIC) downgrade -1

.PHONY: revision
revision: ## Autogenerate a migration; pass MESSAGE="describe the change"
	@if [[ -z "$(MESSAGE)" ]]; then \
		echo 'Usage: make revision MESSAGE="describe the change"'; exit 1; \
	fi
	$(ALEMBIC) revision --autogenerate -m "$(MESSAGE)"

.PHONY: clean
clean: ## Remove caches and build artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage src/*.egg-info
