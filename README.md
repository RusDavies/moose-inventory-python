# moose-inventory

`moose-inventory` is a command-line tool for managing dynamic inventories for [Ansible](https://www.ansible.com/). This package is the Python implementation of the original Ruby [`moose-inventory`](https://github.com/RusDavies/moose-inventory) tool, with the same basic job: keep hosts, groups, variables, and inventory metadata in a database and expose them through a CLI that Ansible can consume.

If you are here to use the tool, start with installation, configuration, and the examples below. Development, release, and maintenance notes live in the `docs/` directory where they belong, safely away from the front desk.

## Installation

Install the base package from PyPI:

```bash
python -m pip install moose-inventory
```

This installs the `moose-inventory` command and includes SQLite support.

For MySQL/MariaDB or PostgreSQL database support, install the matching extra:

```bash
python -m pip install 'moose-inventory[mysql]'
python -m pip install 'moose-inventory[postgresql]'
```

Check that the command is available:

```bash
moose-inventory version
moose-inventory help
```

## Configuration

`moose-inventory` uses a YAML configuration file. The configuration has a required `general` section and one or more environment sections.

A minimal SQLite configuration looks like this:

```yaml
general:
  defaultenv: dev

dev:
  db:
    adapter: sqlite3
    file: ./inventory.db
```

A configuration with multiple environments might look like this:

```yaml
general:
  defaultenv: dev

dev:
  db:
    adapter: sqlite3
    file: ./inventory-dev.db

ops_mysql:
  db:
    adapter: mysql
    host: localhost
    database: inventory
    user: inventory_user
    password_env: MOOSE_INVENTORY_MYSQL_PASSWORD

ops_postgres:
  db:
    adapter: postgresql
    host: localhost
    database: inventory
    user: inventory_user
    password_env: MOOSE_INVENTORY_POSTGRES_PASSWORD
```

Prefer `password_env` for MySQL/MariaDB and PostgreSQL passwords. It keeps reusable configuration files from containing plaintext secrets:

```bash
export MOOSE_INVENTORY_MYSQL_PASSWORD='use-a-real-secret-here'
moose-inventory --config ./config.yml --env ops_mysql host list
```

### Configuration file locations

The configuration file can be supplied explicitly:

```bash
moose-inventory --config ./config.yml host list
```

If `--config` is not supplied, the command searches the standard Moose Tools configuration locations, including project-local, user-local, and system-level paths.

Use `--env` to select an environment section. If `--env` is omitted, the section named by `general.defaultenv` is used:

```bash
moose-inventory --config ./config.yml --env dev host list
```

## Basic usage

Create and inspect inventory records:

```bash
moose-inventory --config ./config.yml database migrate
moose-inventory --config ./config.yml host add web01 --groups web
moose-inventory --config ./config.yml host addvar web01 os=fedora
moose-inventory --config ./config.yml group addvar web role=frontend
moose-inventory --config ./config.yml host list
moose-inventory --config ./config.yml group list
```

Ask the command for help when you forget the shape of a subcommand, as all civilized people do constantly:

```bash
moose-inventory help
moose-inventory help host
moose-inventory host help add
moose-inventory help group
```

## Output formats

Many read operations support `--format`:

```bash
moose-inventory --config ./config.yml --format json host list
moose-inventory --config ./config.yml --format pjson host list
moose-inventory --config ./config.yml --format yaml group list
```

Supported formats are:

- `json` — compact JSON
- `pjson` — pretty-printed JSON
- `yaml` — YAML

## Dry runs and destructive commands

Mutating commands support `--dry-run` so you can preview changes before writing them:

```bash
moose-inventory --config ./config.yml host add web02 --groups web --dry-run
moose-inventory --config ./config.yml group rm old-web --dry-run
```

For automation and review workflows, combine `--dry-run` with `--plan-format`:

```bash
moose-inventory --config ./config.yml host add web02 --groups web --dry-run --plan-format pjson
```

Destructive commands require explicit confirmation with `--yes` unless you are only doing a dry run:

```bash
moose-inventory --config ./config.yml host rm old-web01 --dry-run
moose-inventory --config ./config.yml host rm old-web01 --yes
```

## Import and export snapshots

Export the full inventory as a portable YAML or JSON snapshot:

```bash
moose-inventory --config ./config.yml --format yaml export ./inventory.yml
moose-inventory --config ./config.yml --format pjson export
```

Preview an import before writing anything:

```bash
moose-inventory --config ./config.yml import ./inventory.yml --preview
moose-inventory --config ./config.yml import ./inventory.yml --preview --preview-format pjson
```

Apply the import:

```bash
moose-inventory --config ./config.yml import ./inventory.yml
```

Imports are additive and update-oriented: they create missing hosts and groups, add missing associations and tags, and create or update variables from the snapshot. They do not delete existing inventory records that are absent from the file.

## Inventory health checks

Run `doctor` to check inventory health:

```bash
moose-inventory --config ./config.yml doctor
```

Use a machine-readable format in CI or automation:

```bash
moose-inventory --config ./config.yml --format pjson doctor
```

The doctor command checks configuration, password hygiene, hosts only in `ungrouped`, orphan or empty groups, suspicious duplicate-ish names, invalid variable rows, and group cycles.

## Ansible dynamic inventory

`moose-inventory` can be used as an Ansible dynamic inventory source.

List the inventory:

```bash
moose-inventory --config ./config.yml --list
```

Get host variables for one host:

```bash
moose-inventory --config ./config.yml --host web01
```

You can also call the underlying Ansible-oriented commands explicitly:

```bash
moose-inventory --config ./config.yml --ansible group list
moose-inventory --config ./config.yml --ansible host listvars web01
```

## Read-only console

For manual browsing, open the read-only console:

```bash
moose-inventory --config ./config.yml console
```

Useful console commands include:

```text
hosts
groups
host web01
group web
tags host web01
tags group web
audit 20
help
quit
```

## Migrating from the Ruby version

The Python package is intended as a replacement for the Ruby `moose-inventory` CLI. Before switching production automation, export from the Ruby-backed inventory and import into a test Python-backed database:

```bash
ruby-moose-inventory --config ./ruby-config.yml export ./moose-snapshot.yml
moose-inventory --config ./python-test.yml import ./moose-snapshot.yml --preview
moose-inventory --config ./python-test.yml import ./moose-snapshot.yml
moose-inventory --config ./python-test.yml doctor
moose-inventory --config ./python-test.yml export ./roundtrip.yml
```

Compare the round-tripped snapshot and run your Ansible inventory checks before pointing automation at the new database.

## More documentation

- User guide: `docs/user-guide.md`
- Database backend notes: `docs/backend-adapters.md`
- Release/package operations: `docs/release.md`
- Ruby compatibility notes: `docs/compatibility/`

## Development

For contributors working from a checkout:

```bash
python -m pip install -e '.[dev,postgresql,mysql]'
./scripts/check.sh
```

The check script runs tests, linting, type checking, package build, and package metadata validation.
