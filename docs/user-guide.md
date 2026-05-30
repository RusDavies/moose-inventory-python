# Moose Inventory Python CLI User Guide

This package provides the `moose-inventory` command as a Python replacement for the Ruby CLI. The public contract is the command-line behavior: commands, flags, YAML config shape, database schema, snapshot files, and Ansible dynamic inventory output.

## Install

From PyPI, once published:

```bash
python -m pip install moose-inventory
```

For database extras:

```bash
python -m pip install 'moose-inventory[mysql]'
python -m pip install 'moose-inventory[postgresql]'
```

From a local checkout:

```bash
python -m pip install -e '.[dev]'
moose-inventory version
```

## Configure

Use the same YAML shape as the Ruby CLI:

```yaml
general:
  defaultenv: dev
dev:
  db:
    adapter: sqlite3
    file: ./inventory.db
```

Run with an explicit config while testing:

```bash
moose-inventory --config ./config.yml database status
moose-inventory --config ./config.yml doctor
```

For MySQL/MariaDB and PostgreSQL examples, see `docs/backend-adapters.md`.

## Basic usage

```bash
moose-inventory --config ./config.yml host add web01 --groups web
moose-inventory --config ./config.yml host addvar web01 os=fedora
moose-inventory --config ./config.yml group addvar web role=frontend
moose-inventory --config ./config.yml host list
moose-inventory --config ./config.yml group list
```

Destructive commands require `--yes` unless using `--dry-run`:

```bash
moose-inventory --config ./config.yml host rm web01 --dry-run
moose-inventory --config ./config.yml host rm web01 --yes
```

## Verify inventory health

Run doctor before and after migration work:

```bash
moose-inventory --config ./config.yml doctor
```

Doctor checks database config, plaintext password use, hosts only in `ungrouped`, orphan/empty groups, duplicate-ish names, invalid variable rows, and group cycles.

## Export before switching from Ruby

Before replacing a Ruby installation, export a snapshot from the Ruby CLI:

```bash
ruby-moose-inventory --config ./config.yml export ./moose-snapshot.yml
```

Then preview and import with the Python CLI against a test database:

```bash
moose-inventory --config ./python-test.yml import ./moose-snapshot.yml --preview
moose-inventory --config ./python-test.yml import ./moose-snapshot.yml
moose-inventory --config ./python-test.yml export ./roundtrip.yml
```

Compare the exported snapshot shape and run `doctor` before pointing automation at the Python-backed database.

## Ansible dynamic inventory

The Ruby-compatible aliases are preserved:

```bash
moose-inventory --config ./config.yml --list
moose-inventory --config ./config.yml --host web01
```

You can also call the underlying commands explicitly:

```bash
moose-inventory --config ./config.yml --ansible group list
moose-inventory --config ./config.yml --ansible host listvars web01
```

Ansible mode normalizes output to JSON-compatible formats when needed.

## Read-only browsing

For manual inspection:

```bash
moose-inventory --config ./config.yml console
```

Console commands include `hosts`, `groups`, `host NAME`, `group NAME`, `tags host NAME`, `tags group NAME`, `audit [LIMIT]`, `help`, and `quit`.
