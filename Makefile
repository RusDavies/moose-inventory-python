.PHONY: help test coverage lint format typecheck build package check clean

help:
	@scripts/dev.sh help

test:
	@scripts/dev.sh test

coverage:
	@scripts/dev.sh coverage

lint:
	@scripts/dev.sh lint

format:
	@scripts/dev.sh format

typecheck:
	@scripts/dev.sh typecheck

build:
	@scripts/dev.sh build

package:
	@scripts/dev.sh package

check:
	@scripts/dev.sh check

clean:
	rm -rf build dist .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
