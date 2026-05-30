#!/usr/bin/env bash
set -euo pipefail

python -m pytest "$@"
python -m ruff check src tests
python -m mypy
rm -rf dist
python -m build
python -m twine check dist/*
