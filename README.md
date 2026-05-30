# Moose Inventory Python

Python CLI/package replacement for the Ruby `moose-inventory` command.

## User guide

See `docs/user-guide.md` for installation, configuration, Ruby migration, doctor, snapshot, Ansible, and read-only console usage.

## Database backends

The Python CLI supports the Ruby-compatible `sqlite3`, `mysql`, and `postgresql` adapter names. SQLite works with the base install; MySQL/MariaDB and PostgreSQL use optional extras:

```bash
python -m pip install 'moose-inventory[mysql]'
python -m pip install 'moose-inventory[postgresql]'
```

See `docs/backend-adapters.md` for config examples and adapter smoke-test coverage.

## Release operations

See `docs/release.md` for PyPI publication, ownership, artifact integrity, vulnerability intake, and release evidence expectations.

## Development commands

Install development dependencies first:

```bash
python -m pip install -e '.[dev]'
```

Common checks are available through either `make` targets or `scripts/dev.sh`:

```bash
make test       # python -m pytest
make coverage   # pytest with coverage report
make lint       # ruff check src tests
make format     # ruff format plus import-order fixes
make typecheck  # mypy
make build      # build sdist/wheel
make package    # twine check dist/*
make check      # full release-readiness gate
```

The CI/release gate used during development is:

```bash
./scripts/check.sh
```
