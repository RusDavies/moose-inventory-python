# Database Backend Adapters

`moose-inventory` keeps the Ruby configuration shape and supports the same database adapter names:

- `sqlite3`
- `mysql` for MySQL or MariaDB, via SQLAlchemy's `mysql+pymysql` dialect
- `postgresql`, via SQLAlchemy's `postgresql+psycopg` dialect

SQLite is installed with the base package. Network database drivers are optional extras so small SQLite-only installs do not pull unused client libraries:

```bash
python -m pip install 'moose-inventory[mysql]'
python -m pip install 'moose-inventory[postgresql]'
python -m pip install 'moose-inventory[mysql,postgresql]'
```

## Configuration examples

SQLite:

```yaml
general:
  defaultenv: dev
dev:
  db:
    adapter: sqlite3
    file: ./inventory.db
```

MySQL / MariaDB:

```yaml
general:
  defaultenv: prod
prod:
  db:
    adapter: mysql
    host: db.example.internal
    database: moose_inventory
    user: moose
    password_env: MOOSE_INVENTORY_DB_PASSWORD
```

PostgreSQL:

```yaml
general:
  defaultenv: prod
prod:
  db:
    adapter: postgresql
    host: db.example.internal
    database: moose_inventory
    user: moose
    password_env: MOOSE_INVENTORY_DB_PASSWORD
```

`password` is accepted for Ruby compatibility, but `password_env` is preferred so plaintext credentials do not live in the config file. `moose-inventory doctor` warns when a plaintext password is present.

## Smoke coverage

The Python test suite includes adapter smoke tests that instantiate SQLAlchemy engines for MySQL/MariaDB and PostgreSQL without opening a network connection. These tests verify:

- Ruby-compatible adapter names are accepted.
- Required keys are validated before engine creation.
- `password` and `password_env` resolution match the Ruby contract.
- Optional DB client dependencies are declared in `pyproject.toml`.

A release gate against real MySQL/MariaDB and PostgreSQL services is still recommended before declaring production support for those backends. Tiny detail, yes, but databases are where optimism goes to die.
