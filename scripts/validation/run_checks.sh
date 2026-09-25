#!/usr/bin/env bash
# QRSIP — fast local verification harness.
#
# Runs the same checks CI runs, in the same order, and writes a single
# machine-readable summary to reports/verification/local_checks.json so an
# agent or human can inspect the outcome deterministically.
#
# Usage:
#   scripts/validation/run_checks.sh            # full check set
#   scripts/validation/run_checks.sh --fast     # skip security scans
#
# Exit code is 0 only when every required check passed.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

FAST=0
if [[ "${1:-}" == "--fast" ]]; then
  FAST=1
fi

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: virtualenv interpreter not found at $PY" >&2
  echo "Run: make bootstrap" >&2
  exit 2
fi

OUT_DIR="$REPO_ROOT/reports/verification"
mkdir -p "$OUT_DIR"

declare -a NAMES=()
declare -a RESULTS=()
OVERALL=0

run_check() {
  local name="$1"
  shift
  local log="$OUT_DIR/${name}.log"
  if "$@" >"$log" 2>&1; then
    NAMES+=("$name")
    RESULTS+=("pass")
    echo "PASS  $name"
  else
    local code=$?
    NAMES+=("$name")
    RESULTS+=("fail:$code")
    echo "FAIL  $name (exit $code) — see $log"
    OVERALL=1
  fi
}

echo "== QRSIP local verification =="
run_check format "$PY" -m ruff format --check src tests
run_check lint "$PY" -m ruff check src tests
run_check typecheck "$PY" -m mypy src
run_check unit "$PY" -m pytest tests/unit -q
run_check integration "$PY" -m pytest tests/integration -q
run_check contract "$PY" -m pytest tests/contract -q
run_check property "$PY" -m pytest tests/property -q
run_check regression "$PY" -m pytest tests/regression -q
run_check adversarial "$PY" -m pytest tests/adversarial -q
run_check acceptance "$PY" -m pytest tests/acceptance -q

if [[ "$FAST" -eq 0 ]]; then
  if "$PY" -c "import bandit" >/dev/null 2>&1; then
    run_check security_bandit "$PY" -m bandit -q -r src -c pyproject.toml -ll
  else
    echo "SKIP  security_bandit (bandit not installed)"
  fi
  if "$PY" -c "import pip_audit" >/dev/null 2>&1; then
    run_check security_pip_audit "$PY" -m pip_audit --progress-spinner off
  else
    echo "SKIP  security_pip_audit (pip-audit not installed)"
  fi
fi

{
  echo "{"
  echo "  \"checks\": {"
  for i in "${!NAMES[@]}"; do
    comma=","
    if [[ $i -eq $((${#NAMES[@]} - 1)) ]]; then comma=""; fi
    echo "    \"${NAMES[$i]}\": \"${RESULTS[$i]}\"$comma"
  done
  echo "  },"
  echo "  \"overall\": $([ $OVERALL -eq 0 ] && echo '"pass"' || echo '"fail"')"
  echo "}"
} >"$OUT_DIR/local_checks.json"

echo
if [[ $OVERALL -eq 0 ]]; then
  echo "OVERALL: PASS — see $OUT_DIR/local_checks.json"
else
  echo "OVERALL: FAIL — see $OUT_DIR/local_checks.json"
fi
exit $OVERALL
