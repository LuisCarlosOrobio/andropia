# Andropia
#
# The project is two test suites in two languages, in two working directories.
# Running them by hand is how a green suite comes to mean "the half I remembered
# to run passed" — so `make check` is the whole thing, and it is the one command
# to run before pushing.

PYTHON ?= .venv/bin/python
NPM    ?= npm

.DEFAULT_GOAL := help
.PHONY: help check test test-py test-js lint format format-check build dev clean install claude-check

help: ## Show this help
	@grep -hE '^[a-z][a-zA-Z_-]*:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

check: lint test ## Lint and both test suites — run this before pushing
	@echo "ok"

test: test-py test-js ## Both test suites

test-py: ## Simulation, runtime, pack loader
	$(PYTHON) -m pytest tests

test-js: ## Animation stack, pose composition, wire projection
	cd frontend && $(NPM) run --silent test

lint: ## Ruff's lint rules, as configured in pyproject.toml
	$(PYTHON) -m ruff check src tests

# Deliberately not part of `check`. The tree is lint-clean but not
# ruff-format-clean: 12 files are hand-wrapped in ways the formatter would
# redo. Adopting it is a one-time decision with a large, purely cosmetic diff,
# so it is a target you run on purpose rather than something that fails a
# build. Once adopted, fold `format-check` into `check` and delete this note.
format-check: ## Report where the tree differs from ruff format
	$(PYTHON) -m ruff format --diff src tests

format: ## Apply formatting and safe fixes
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests

claude-check: ## One being, two live turns — checks key, credit, model, caching
	$(PYTHON) scripts/claude_check.py

build: ## Bundle the frontend into frontend/dist, which the server serves
	cd frontend && $(NPM) run build

dev: build ## Build, then serve the world at http://127.0.0.1:8600
	@echo "world:      http://127.0.0.1:8600"
	@echo "pose tuner: http://127.0.0.1:8600/tune"
	$(PYTHON) -m andropia.runtime.server

install: ## Install both sides into an existing venv, plus node modules
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[runtime,dev]"
	cd frontend && $(NPM) install

clean: ## Remove build output and caches. Never sources or assets.
	rm -rf frontend/dist .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -not -path "./.venv/*" -exec rm -rf {} +
