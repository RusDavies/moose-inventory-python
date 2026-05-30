#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/dev.sh COMMAND

Development and verification commands:
  test       Run pytest
  coverage   Run pytest with coverage report
  lint       Run ruff lint checks
  format     Format/check import order with ruff
  typecheck  Run mypy
  build      Build sdist and wheel artifacts
  package    Validate dist/* with twine
  check      Run the full release-readiness gate
USAGE
}

command="${1:-check}"
shift || true

case "${command}" in
  test)
    python -m pytest "$@"
    ;;
  coverage)
    python -m pytest --cov=moose_inventory --cov-report=term-missing "$@"
    ;;
  lint)
    python -m ruff check src tests "$@"
    ;;
  format)
    python -m ruff format src tests "$@"
    python -m ruff check --select I --fix src tests
    ;;
  typecheck)
    python -m mypy "$@"
    ;;
  build)
    python -m build "$@"
    ;;
  package)
    python -m twine check dist/* "$@"
    ;;
  check)
    "$(dirname "$0")/check.sh" "$@"
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    usage >&2
    echo "ERROR: Unknown development command '${command}'." >&2
    exit 2
    ;;
esac
