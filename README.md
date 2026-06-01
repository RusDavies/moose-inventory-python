# Moose Inventory Python

Python CLI/package replacement for the Ruby [`moose-inventory`](https://github.com/RusDavies/moose-inventory) command.

Install from PyPI:

```bash
python -m pip install moose-inventory
```

Check the installed CLI:

```bash
moose-inventory version
moose-inventory help
```

## User guide

See the [user guide](https://github.com/RusDavies/moose-inventory-python/blob/master/docs/user-guide.md) for installation, configuration, Ruby migration, doctor, snapshot, Ansible, and read-only console usage.

## Database backends

The Python CLI supports the Ruby-compatible `sqlite3`, `mysql`, and `postgresql` adapter names.

SQLite works with the base install. MySQL/MariaDB and PostgreSQL use optional extras:

```bash
python -m pip install 'moose-inventory[mysql]'
python -m pip install 'moose-inventory[postgresql]'
```

See [database backend adapters](https://github.com/RusDavies/moose-inventory-python/blob/master/docs/backend-adapters.md) for config examples and adapter smoke-test coverage.

## Release operations

Release and security-maintenance notes live in [release operations](https://github.com/RusDavies/moose-inventory-python/blob/master/docs/release.md).

Publication uses PyPI Trusted Publishing from GitHub Actions.

## Development commands

Install development dependencies first:

```bash
python -m pip install -e '.[dev]'
```

Common checks are available through either `make` targets or `scripts/dev.sh`:

```bash
make test
make coverage
make lint
make format
make typecheck
make build
make package
make check
```

The full CI/release gate used during development is:

```bash
./scripts/check.sh
```
