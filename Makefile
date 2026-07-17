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
FRONTEND_NODE_VERSION := $(shell cat frontend/.nvmrc)
NVM_DIR ?= $(HOME)/.nvm

define RUN_FRONTEND
bash -lc 'set -e; NVM_SH="$${NVM_DIR:-$(NVM_DIR)}/nvm.sh"; if [ ! -s "$$NVM_SH" ]; then echo "nvm not found at $$NVM_SH; install nvm and run nvm install $(FRONTEND_NODE_VERSION)" >&2; exit 1; fi; . "$$NVM_SH"; nvm use $(FRONTEND_NODE_VERSION) >/dev/null; cd frontend; $(1)'
endef

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
	@echo "  make coverage-gate     Core+services coverage enforcing pyproject fail_under (CI gate)"
	@echo "  make deps-check        Dependency hygiene (deptry): unused/missing/misplaced deps"
	@echo "  make vocabularies      Export backend vocabularies to frontend/src/generated/"
	@echo "  make openapi           Export the OpenAPI schema to frontend/openapi.json"
	@echo "  make contracts         All backend-owned frontend artifacts (vocabularies + openapi)"
	@echo "  make lint              Ruff lint (no fixes)"
	@echo "  make lint-fix          Ruff lint with --fix"
	@echo "  make format            Ruff format"
	@echo "  make typecheck         Mypy over the full backend tree"
	@echo "  make typecheck-core    Mypy over backend.core only (strict)"
	@echo "  make check             lint + typecheck-core + test-core (fast gate)"
	@echo "  make check-all         lint + typecheck-core + test (core + services) + frontend lint/typecheck/tests on Node $(FRONTEND_NODE_VERSION)"
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

# fail_under is read from backend/pyproject.toml [tool.coverage.report]; do
# not duplicate the number here. --cov-config is required because coverage.py
# only auto-discovers config relative to cwd, and this target (like CI) runs
# from the repo root, not backend/.
.PHONY: coverage-gate
coverage-gate:
	$(PYTEST) $(CORE_TESTS) $(SERVICES_TESTS) --cov=backend --cov-config=backend/pyproject.toml \
		--cov-report=term --cov-report=xml -q

.PHONY: lint
lint:
	$(RUFF) check backend

.PHONY: lint-fix
lint-fix:
	$(RUFF) check --fix backend

.PHONY: format
format:
	$(RUFF) format backend

.PHONY: import-lint
import-lint:
	uv run --project backend lint-imports --config backend/pyproject.toml

.PHONY: deps-check
deps-check:
	cd backend && uv run deptry .

.PHONY: vocabularies
vocabularies:
	$(PY) backend/scripts/export_vocabularies.py

.PHONY: openapi
openapi:
	$(PY) backend/scripts/export_openapi.py

# Every backend-owned artifact the frontend generates from. CI runs this then
# `git diff --exit-code`, so a contract change that skips it fails the build.
.PHONY: contracts
contracts: vocabularies openapi

.PHONY: typecheck
typecheck:
	$(MYPY) -p backend

.PHONY: typecheck-core
typecheck-core:
	$(MYPY) -p backend.core

# Strict-typing ratchet: packages driven to zero mypy errors under the strict
# ``disallow_untyped_defs`` override (see backend/pyproject.toml). Gated in
# ``check`` / ``check-all`` so these modules cannot regress. Grow RATCHET_PKGS as
# more of the tree is cleaned; the long-term goal is the full ``typecheck`` target.
RATCHET_PKGS := backend.services.guided_task backend.steps

.PHONY: typecheck-ratchet
typecheck-ratchet:
	$(MYPY) $(foreach pkg,$(RATCHET_PKGS),-p $(pkg))

.PHONY: frontend-build
frontend-build:
	$(call RUN_FRONTEND,npm ci --no-audit --no-fund && npm run build)

.PHONY: frontend-test
frontend-test:
	$(call RUN_FRONTEND,npm run test --silent)

.PHONY: frontend-typecheck
frontend-typecheck:
	$(call RUN_FRONTEND,npm run typecheck)

.PHONY: frontend-lint
frontend-lint:
	$(call RUN_FRONTEND,npm run lint && npm run format:check && npm run knip)

.PHONY: test-integration
test-integration:
	$(PYTEST) -m integration backend/tests/integration -v

.PHONY: check
check: lint typecheck-core typecheck-ratchet test-core

.PHONY: check-all
check-all: lint import-lint typecheck-core typecheck-ratchet test-core test-services frontend-lint frontend-typecheck frontend-test

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
