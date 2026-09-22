#!/usr/bin/env bash
# QRSIP — development bootstrap script
#
# This script prepares a local development environment from a fresh clone.
# It is idempotent and safe to run multiple times.
#
# Usage:
#   ./scripts/bootstrap/dev_bootstrap.sh
#
# This is the canonical bootstrap path for new contributors and for the
# fresh-environment acceptance test (spec §48).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
PYTHON_BIN="python3"

echo "QRSIP dev bootstrap"
echo "==================="
echo "repo root: ${REPO_ROOT}"
echo "python:    ${PYTHON_BIN} ($(python3 --version 2>&1 || true))"

# ------------------------------------------------------------------
# 1. Virtual environment
# ------------------------------------------------------------------
if [ ! -d "${VENV_DIR}" ]; then
    echo "creating virtual environment at ${VENV_DIR}"
    ${PYTHON_BIN} -m venv "${VENV_DIR}"
fi

# Activate venv for the rest of the script.
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# Ensure pip is recent enough.
pip install --quiet --upgrade pip setuptools wheel

# ------------------------------------------------------------------
# 2. Install package + dev dependencies
# ------------------------------------------------------------------
echo "installing qrsip + dev dependencies"

# Try editable install; if git is not yet initialized/committed, fall back
# to a path install so bootstrap can complete before the first commit.
if git rev-parse HEAD >/dev/null 2>&1; then
    pip install -e "${REPO_ROOT}[dev]" --quiet
else
    echo "git HEAD not available; using path install instead of editable"
    pip install "${REPO_ROOT}[dev]" --quiet
fi

# Freeze for reproducibility + security checks.
pip freeze | sed 's/=*//' > "${REPO_ROOT}/requirements-frozen.txt"

# ------------------------------------------------------------------
# 3. Verification
# ------------------------------------------------------------------
echo "verifying installation"
if command -v qrsip >/dev/null 2>&1; then
    qrsip --version
else
    echo "ERROR: qrsip not on PATH after install" >&2
    exit 1
fi

echo "bootstrap complete"
echo "next steps:"
echo "  make test        # run the test suite"
echo "  make ci          # full local CI pipeline"
echo "  qrsip doctor     # environment health check"
