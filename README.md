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

## Host and group relationships

Hosts can belong to one or more groups. New hosts start in the automatic `ungrouped` group unless you place them elsewhere. When a host gains a real group association, `ungrouped` is removed automatically. When its last real group association is removed, `ungrouped` is added back.

```bash
moose-inventory --config ./config.yml host add web01
moose-inventory --config ./config.yml group add web
moose-inventory --config ./config.yml host addgroup web01 web
moose-inventory --config ./config.yml group addhost web web02
moose-inventory --config ./config.yml host rmgroup web01 web --yes
moose-inventory --config ./config.yml group rmhost web web02 --yes
```

Groups can also have child groups. This lets you model nested inventory structure without flattening everything into a sad pile of names.

```bash
moose-inventory --config ./config.yml group add region-east web
moose-inventory --config ./config.yml group addchild region-east web
moose-inventory --config ./config.yml group rmchild region-east web --yes
```

Use `--recursive` when deleting a group and you intentionally want orphaned child groups removed too. Use `--delete-orphans` with `group rmchild` when removing a parent-child relationship should also delete child subtrees that become orphaned by that removal.

```bash
moose-inventory --config ./config.yml group rm old-parent --recursive --yes
moose-inventory --config ./config.yml group rmchild parent child --delete-orphans --yes
```

## Variables, tags, and filtered lists

Host and group variables are exposed to inventory consumers. Use them for data Ansible should see:

```bash
moose-inventory --config ./config.yml host addvar web01 os=fedora owner=platform
moose-inventory --config ./config.yml group addvar web role=frontend
moose-inventory --config ./config.yml host listvars web01
moose-inventory --config ./config.yml group listvars web
moose-inventory --config ./config.yml host rmvar web01 owner --yes
```

Metadata tags are separate from Ansible variables. Use them for operational labels such as environment, owner, lifecycle, location, role, or criticality when you want searchable inventory metadata without exposing it as host/group vars.

```bash
moose-inventory --config ./config.yml host addtag web01 prod critical owner-platform
moose-inventory --config ./config.yml host listtags web01
moose-inventory --config ./config.yml host rmtag web01 critical --yes

moose-inventory --config ./config.yml group addtag web frontend public-edge
moose-inventory --config ./config.yml group listtags web --format json
```

Tag names are normalized to lowercase and deduplicated.

Host listings can be filtered by group, tag, and variable. Multiple filters are treated as an AND: the host must match all requested groups, tags, and variable key/value pairs.

```bash
moose-inventory --config ./config.yml host list --group web --tag prod --var os=fedora --format yaml
```

## Audit log and database lifecycle

Successful mutating commands are recorded in a small append-only audit log. Dry runs are not recorded, because they did not change anything. Shocking restraint, really.

```bash
moose-inventory --config ./config.yml audit list
moose-inventory --config ./config.yml audit list --limit 100
moose-inventory --config ./config.yml audit list --format pjson
```

Database lifecycle commands live under `database`; `db` is an alias.

```bash
moose-inventory --config ./config.yml db status
moose-inventory --config ./config.yml db doctor
moose-inventory --config ./config.yml db migrate
moose-inventory --config ./config.yml db backup ./backup/moose-inventory.sqlite3
```

`db migrate` creates missing schema tables and records the current schema version. `db backup` is supported for SQLite databases only; for MySQL/MariaDB and PostgreSQL, use native database backup tools such as `mysqldump`, `mariadb-dump`, `pg_dump`, or managed-service snapshots.

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

To persist data from an Ansible run back into the inventory, call `moose-inventory` from a local task or from your inventory shim. For example:

```yaml
- set_fact:
    discovered_role: frontend

- name: Record discovered host role in Moose Inventory
  delegate_to: localhost
  ansible.builtin.command:
    argv:
      - moose-inventory
      - --config
      - ./config.yml
      - host
      - addvar
      - "{{ inventory_hostname }}"
      - "role={{ discovered_role }}"
```

If you wrap `moose-inventory` in a shell shim, pass Ansible's arguments through as quoted `"$@"` so names and values containing spaces survive the trip through the shell-shaped cheese grater.

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
