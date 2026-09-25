# QRSIP — Makefile
# Canonical local development commands.
#
# This mirrors the CI pipeline where possible so local verification matches CI.
# Every target should be reproducible and idempotent.

.PHONY: help bootstrap test lint format typecheck security validate build ci clean doctor status

HELP_MSG := \
	"QRSIP — Quantitative Research & Strategy Intelligence Platform" \
	"" \
	"Usage: make [target]" \
	"" \
	"Targets:" \
	"  bootstrap   Install package + dev dependencies in the current venv" \
	"  test        Run the pytest suite" \
	"  lint        Run ruff lint" \
	"  format      Run ruff format (check mode)" \
	"  format-fix  Run ruff format (write mode)" \
	"  typecheck   Run mypy strict" \
	"  security    Run bandit + pip-audit" \
	"  validate    Run format + lint + typecheck + test" \
	"  build       Build the wheel" \
	"  ci          Local mirror of the CI pipeline" \
	"  doctor      Run qrsip doctor" \
	"  status      Show PROJECT_STATUS.md" \
	"  clean       Remove build artifacts and caches" \
	"  help        Show this message"

help:
	@echo "$$(HELP_MSG)" | tr '\n' '\n'

bootstrap:
	@pip install -e ".[dev]" --quiet
	@pip freeze --exclude-editable | sed 's/=*//' > requirements-frozen.txt
	@echo "bootstrap complete"

test:
	@pytest -v

lint:
	@ruff check src tests

format:
	@ruff format --check src tests

format-fix:
	@ruff format src tests

typecheck:
	@mypy src

security:
	@bandit -r src -c pyproject.toml -ll
	@pip-audit -r requirements-frozen.txt

validate: format lint typecheck test

build:
	@python -m build --outdir dist

ci: bootstrap validate security build
	@echo "ci pipeline complete"

doctor:
	@qrsip doctor

status:
	@qrsip status

clean:
	@rm -rf build dist .eggs *.egg-info
	@rm -rf .pytest_cache .coverage htmlcov coverage.xml
	@rm -rf .mypy_cache .ruff_cache __pycache__
	@rm -rf src/**/__pycache__ src/**/*.pyc
	@rm -f requirements-frozen.txt
	@echo "clean complete"
