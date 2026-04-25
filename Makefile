# Cognitive Companion — repository-level developer tasks.
#
# Run from the project root. All targets use the uv system in the
# backend directory. Override with ``make PY="uv run --python 3.12" test``
# if you want a different interpreter.

PY      ?= uv run --project backend python
PYTEST  := $(PY) -m pytest
RUFF    := $(PY) -m ruff
MYPY    := $(PY) -m mypy --config-file backend/pyproject.toml

# Directories the layer-specific targets restrict themselves to.
CORE_PKG       := backend/core
CORE_TESTS     := backend/tests/core
SERVICES_PKG   := backend/services
SERVICES_TESTS := backend/tests/services

.PHONY: help
help:
	@echo "Cognitive Companion — developer targets"
	@echo ""
	@echo "  make test              Run the full backend test suite"
	@echo "  make test-core         Run only the backend/core test suite"
	@echo "  make test-services     Run only the backend/services test suite"
	@echo "  make coverage          Run core tests with branch coverage (terminal)"
	@echo "  make coverage-services Coverage for services (terminal)"
	@echo "  make coverage-html     Coverage + HTML report under ./htmlcov"
	@echo "  make lint              Ruff lint (no fixes)"
	@echo "  make lint-fix          Ruff lint with --fix"
	@echo "  make format            Ruff format"
	@echo "  make typecheck         Mypy over the full backend tree"
	@echo "  make typecheck-core    Mypy over backend.core only (strict)"
	@echo "  make check             lint + typecheck-core + test-core (fast gate)"
	@echo "  make check-all         lint + typecheck-core + test (core + services)"
	@echo "  make migrate           Run Alembic migrations (upgrade to head)"
	@echo "  make migration         Generate new Alembic migration (autogenerate)"
	@echo "  make migration-history Show Alembic migration history"
	@echo "  make init-db           Initialize PostgreSQL database and run migrations"
	@echo "  make clean             Remove caches & coverage artifacts"

.PHONY: test
test:
	$(PYTEST) backend/tests

.PHONY: test-core
test-core:
	$(PYTEST) $(CORE_TESTS) -v

.PHONY: test-services
test-services:
	$(PYTEST) $(SERVICES_TESTS) -v

.PHONY: coverage
coverage:
	$(PYTEST) $(CORE_TESTS) --cov=$(CORE_PKG) --cov-report=term-missing

.PHONY: coverage-services
coverage-services:
	$(PYTEST) $(SERVICES_TESTS) --cov=$(SERVICES_PKG) --cov-report=term-missing --cov-branch

.PHONY: coverage-html
coverage-html:
	$(PYTEST) $(CORE_TESTS) --cov=$(CORE_PKG) --cov-report=html --cov-report=term
	@echo "HTML report: file://$(CURDIR)/htmlcov/index.html"

.PHONY: lint
lint:
	$(RUFF) check backend

.PHONY: lint-fix
lint-fix:
	$(RUFF) check --fix backend

.PHONY: format
format:
	$(RUFF) format backend

.PHONY: typecheck
typecheck:
	$(MYPY) -p backend

.PHONY: typecheck-core
typecheck-core:
	$(MYPY) -p backend.core

.PHONY: check
check: lint typecheck-core test-core

.PHONY: check-all
check-all: lint typecheck-core test-core test-services

.PHONY: migrate
migrate:
	cd backend && uv run alembic upgrade head

.PHONY: migration
migration:
	cd backend && uv run alembic revision --autogenerate

.PHONY: migration-history
migration-history:
	cd backend && uv run alembic history

.PHONY: init-db
init-db:
	uv run --project backend python scripts/init_db.py

.PHONY: clean
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
