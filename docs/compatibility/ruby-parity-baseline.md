# Ruby Parity Baseline

Status: initial compatibility baseline for the Python CLI port.

This document records the Ruby `moose-inventory` behavior that the Python CLI package must treat as the replacement contract unless Russ explicitly approves a compatibility break.

Reference implementation:

- Ruby repo: `../moose-inventory`
- Python repo: `../moose-inventory-python`
- Ruby executable: `moose-inventory`
- Python executable target: `moose-inventory`

The Python project is a CLI package. Its public API is the command line, database/schema compatibility, config compatibility, snapshot compatibility, and Ansible dynamic-inventory behavior. Importable Python modules are implementation details unless a future decision says otherwise.

## Compatibility priority

When behavior is unclear, use this priority order:

1. Ruby regression specs and fixtures.
2. Ruby docs under `../moose-inventory/docs/`.
3. Ruby README examples.
4. Current Ruby CLI behavior from the executable.
5. Ruby implementation details, only where the external contract is otherwise ambiguous.

Do not treat a convenient Python library/API design as permission to change CLI behavior. That is how ports become fan fiction.

## Global command behavior

The executable name must be `moose-inventory`.

Global flags parsed before command dispatch:

- `--config FILE`: explicit YAML config file; must exist; takes precedence over all default search paths.
- `--env ENV`: selects an environment section from the config file.
- `--format yaml|json|pjson`: output format for documented read/list/get/report commands; default is `json`.
- `--ansible`: forces Ansible-compatible mode for relevant responders.
- `--trace`: enables more complete exception output in database transaction error paths.

Ansible aliases:

- `--list` maps to `group list` and enables Ansible mode.
- `--host HOSTNAME` maps to `host listvars HOSTNAME` and enables Ansible mode.

Top-level help compatibility targets:

- `moose-inventory help`
- `moose-inventory help group`
- `moose-inventory group help add`

Exact formatting of generated framework help is a compatibility surface only where protected by Ruby specs/docs/examples, but available commands, aliases, and documented flags are required.

## Config compatibility

The YAML config format must preserve the Ruby structure:

```yaml
general:
  defaultenv: moose_dev

moose_dev:
  db:
    adapter: sqlite3
    file: ~/.moose/db/dev.db
```

Rules:

- `general.defaultenv` is mandatory unless `--env` selects an environment explicitly.
- Environment sections are top-level YAML mappings.
- Each environment contains `db` settings.
- Supported adapters are `sqlite3`, `mysql`, and `postgresql`.
- SQLite requires `file` and creates parent directories automatically.
- MySQL/MariaDB and PostgreSQL require `host`, `database`, `user`, and either `password_env` or legacy `password`.
- `password_env` is preferred; plaintext `password` remains supported for compatibility.
- YAML must be loaded safely, without arbitrary object construction.

Default config search order:

1. `./.moose-tools/inventory/config`
2. `~/.moose-tools/inventory/config`
3. `~/local/etc/moose-tools/inventory/config`
4. `/etc/moose-tools/inventory/config`

## Command matrix

### Top level

- `version`
- `doctor [--format yaml|json|pjson]`
- `export [FILE]`
- `import FILE [--preview] [--preview-format yaml|json|pjson]`
- `console`
- `audit ACTION`
- `db ACTION`
- `database ACTION` alias for `db`
- `group ACTION`
- `host ACTION`

### Database lifecycle commands

- `db status`
- `db doctor`
- `db migrate`
- `db backup FILE`
- `database status`
- `database doctor`
- `database migrate`
- `database backup FILE`

SQLite backup copies the configured database file. Server-backed database dump/restore remains outside the CLI.

### Audit commands

- `audit list [--limit N] [--format yaml|json|pjson]`

Audit records are append-only mutation evidence. Dry runs must not create mutation audit records.

### Host commands

- `host add HOSTNAME_1 [HOSTNAME_2 ...] [--groups GROUP1,GROUP2] [--dry-run] [--plan-format yaml|json|pjson]`
- `host rm HOSTNAME_1 [HOSTNAME_2 ...] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `host get HOST_1 [HOST_2 ...]`
- `host list [--group GROUPS] [--tag TAGS] [--var KEY=VALUE,...]`
- `host addgroup HOSTNAME GROUPNAME [GROUPNAME ...] [--dry-run] [--plan-format yaml|json|pjson]`
- `host rmgroup HOSTNAME GROUPNAME [GROUPNAME ...] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `host addvar HOSTNAME VARNAME=VALUE [VARNAME=VALUE ...] [--dry-run] [--plan-format yaml|json|pjson]`
- `host rmvar HOSTNAME VARNAME [VARNAME ...] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `host listvar HOSTNAME [HOSTNAME ...]`
- `host listvars HOSTNAME [HOSTNAME ...]`
- `host addtag HOST TAG_1 [TAG_2 ...]`
- `host rmtag HOST TAG_1 [TAG_2 ...] [--yes]`
- `host listtags HOST [--format yaml|json|pjson]`

### Group commands

- `group add NAME [NAME ...] [--hosts HOST1,HOST2] [--dry-run] [--plan-format yaml|json|pjson]`
- `group rm NAME [NAME ...] [--recursive] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `group get GROUP_1 [GROUP_2 ...]`
- `group list`
- `group addhost GROUPNAME HOSTNAME_1 [HOSTNAME_2 ...] [--dry-run] [--plan-format yaml|json|pjson]`
- `group rmhost GROUPNAME HOSTNAME_1 [HOSTNAME_2 ...] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `group addchild PARENTGROUP CHILDGROUP_1 [CHILDGROUP_2 ...] [--dry-run] [--plan-format yaml|json|pjson]`
- `group rmchild PARENTGROUP CHILDGROUP_1 [CHILDGROUP_2 ...] [--delete-orphans] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `group addvar GROUP VARNAME=VALUE [VARNAME=VALUE ...] [--dry-run] [--plan-format yaml|json|pjson]`
- `group rmvar GROUP VARNAME [VARNAME ...] [--dry-run] [--yes] [--plan-format yaml|json|pjson]`
- `group listvar GROUP [GROUP ...]`
- `group listvars GROUP [GROUP ...]`
- `group addtag GROUP TAG_1 [TAG_2 ...]`
- `group rmtag GROUP TAG_1 [TAG_2 ...] [--yes]`
- `group listtags GROUP [--format yaml|json|pjson]`

## Database backend and schema baseline

Supported adapters:

- `sqlite3`
- `mysql` for MySQL/MariaDB-compatible servers
- `postgresql`

The Python implementation must preserve Ruby schema version **4** and refuse to operate on databases with a schema version newer than it supports.

Tables:

- `hosts(id, name)` with unique `name`
- `hostvars(id, host_id, name, value)`
- `groups(id, name)` with unique `name`
- `groups_groups(id, parent_id, child_id)`
- `groupvars(id, group_id, name, value)`
- `groups_hosts(id, host_id, group_id)`
- `schema_info(id, version)`
- `audit_events(id, created_at, actor, command, action, entity_type, entity_name, details)`
- `tags(id, name)` with unique non-null `name`
- `hosts_tags(id, host_id, tag_id)`
- `groups_tags(id, group_id, tag_id)`

Required indexes:

- unique `idx_hostvars_host_id_name` on `hostvars(host_id, name)`
- unique `idx_groupvars_group_id_name` on `groupvars(group_id, name)`
- unique `idx_groups_hosts_host_id_group_id` on `groups_hosts(host_id, group_id)`
- unique `idx_groups_groups_parent_id_child_id` on `groups_groups(parent_id, child_id)`
- unique `idx_hosts_tags_host_id_tag_id` on `hosts_tags(host_id, tag_id)`
- unique `idx_groups_tags_group_id_tag_id` on `groups_tags(group_id, tag_id)`
- non-unique `idx_groups_hosts_group_id_host_id` on `groups_hosts(group_id, host_id)`
- non-unique `idx_groups_groups_child_id_parent_id` on `groups_groups(child_id, parent_id)`
- non-unique `idx_hosts_tags_tag_id_host_id` on `hosts_tags(tag_id, host_id)`
- non-unique `idx_groups_tags_tag_id_group_id` on `groups_tags(tag_id, group_id)`

Migration behavior:

- Known migrations run in order.
- Missing schema artifacts are created where Ruby would create them.
- Duplicate cleanup before unique index creation must preserve Ruby semantics: exact duplicates may collapse; conflicting duplicate variable values must fail for manual resolution.
- Mutating commands should be transactional where practical.

## Inventory behavior baseline

Core model:

- hosts
- groups
- host variables
- group variables
- host-group memberships
- group-child relationships
- host/group metadata tags
- append-only audit events

Important rules:

- `ungrouped` is the automatic group name.
- Hosts without explicit non-automatic group memberships should be associated with `ungrouped` according to Ruby behavior.
- Removing the last non-automatic group from a host should restore `ungrouped` where Ruby does.
- The reserved automatic group cannot be created or assigned in ways Ruby rejects.
- Group hierarchy must reject or report circular relationships.
- Host list filters for group, tag, and variable are AND-style filters.
- Missing filters should return empty results rather than broadening results.
- Tag names are normalized by lowercasing, stripping surrounding whitespace, rejecting empty names, and deduplicating.

## Output compatibility baseline

Ruby defines `CLI-OUTPUT-v1`.

Machine-readable compatibility surfaces:

- `--format json|yaml|pjson` output for list/get/report commands.
- `export` snapshot output.
- `doctor --format ...` reports.
- `audit list --format ...` results.
- `--dry-run --plan-format json|yaml|pjson` event plans.
- `listtags --format ...` output.

Rules:

- JSON/YAML/pjson must parse successfully in the declared format.
- Existing top-level keys, nested keys, and event `type` strings must not be renamed or removed without explicit breaking-change approval.
- Additive fields are safer than renamed fields.
- `pjson` is semantically equivalent to `json`; whitespace is not a semantic guarantee.
- YAML scalar formatting is not guaranteed when parsed structure is unchanged.
- Protected human-readable output includes output locked by Ruby regression specs, README examples, release gates, and documented workflows.
- Scripts should prefer machine-readable output over human-readable progress text.

Unsupported formats must fail predictably before mutation.

## Dry-run and destructive-command baseline

Mutating command families with `--dry-run`:

- `host add`, `host rm`
- `group add`, `group rm`
- `host addvar`, `host rmvar`, `group addvar`, `group rmvar`
- `host addgroup`, `host rmgroup`, `group addhost`, `group rmhost`
- `group addchild`, `group rmchild`

Rules:

- Dry-run must not mutate the database.
- Human dry-runs end with `Dry run complete. No changes applied.` where Ruby does.
- `--plan-format yaml|json|pjson` requires `--dry-run`; without `--dry-run`, abort before mutation.
- Plan output is an ordered event envelope with command identity, dry-run marker, `changes_applied: false`, and event entries containing `type` and `payload`.
- Destructive commands require explicit acknowledgement with `--yes` unless run as dry-run.

Destructive command families include host/group removal, variable removal, host/group association removal, child-group dissociation, and tag removal.

## Snapshot baseline

Export shape:

```yaml
version: 1
hosts:
  web01:
    groups:
      - web
    tags:
      - prod
    vars:
      env: prod
groups:
  web:
    children: []
    tags:
      - frontend
    vars:
      role: frontend
```

Rules:

- Snapshot version is `1`.
- Snapshot includes hosts, host variables, host-group memberships, host tags, groups, group variables, child-group relationships, and group tags.
- Host and group keys are sorted by name in Ruby export.
- Host groups/tags and group children/tags are sorted.
- Variable maps are sorted by variable name in Ruby export.
- Export is read-only.
- Import validates before writing.
- Import is additive/update-oriented: create missing entities, add missing associations/tags, and create/update variables found in the snapshot.
- Import must not delete existing inventory records absent from the snapshot.
- Any destructive sync/restore mode requires explicit future requirements, UX, recovery, and approval records.

Import preview shape:

- `schema_version: snapshot-import-preview-v1`
- `changes_applied: false`
- `summary`
- `creates`
- `updates`
- `associations`
- `unchanged`
- `ignored`
- `unsupported_destructive_implications`

Validation rejects malformed snapshots, unsupported versions/fields, unknown references, invalid variable shapes, duplicate normalized keys, whitespace-only names, and circular group hierarchies where Ruby rejects them.

## Ansible compatibility baseline

The Python CLI must preserve Ruby dynamic inventory behavior:

- `moose-inventory --list` behaves as Ansible inventory list output via `group list`.
- `moose-inventory --host HOSTNAME` behaves as host variable lookup via `host listvars HOSTNAME`.
- `--ansible` forces Ansible-compatible mode for relevant responders.
- Ansible mode normalizes incompatible output format selections back to JSON where Ruby does.
- README Ansible examples in the Ruby project remain compatibility guidance until Python docs replace them deliberately.

## Console baseline

Ruby includes a small read-only browsing console. The Python port should implement it for parity or record a specific compatibility decision before deferring it.

Read-only means console commands may inspect hosts, groups, tags, and audit entries but must not mutate inventory.

## Parity test strategy

The Python project should build a compatibility harness before broad feature porting.

Minimum parity evidence:

- Ruby CLI and Python CLI run against disposable SQLite databases.
- Ruby-created DB can be read and mutated by Python.
- Python-created DB can be read and mutated by Ruby.
- For machine-readable output, compare parsed structures, not whitespace.
- For protected human-readable output, compare exact stdout/stderr where Ruby specs/docs/examples require it.
- Compare exit codes for success and failure paths.
- Compare resulting database state after mutating commands.
- Compare snapshot export structures.
- Compare dry-run plan event structures and ordering.
- Smoke-test MySQL/MariaDB and PostgreSQL adapter dispatch/error paths without requiring live servers initially.

## Breaking-change process for the Python port

A breaking change is any intentional difference from the Ruby baseline in:

- command names or aliases
- global or command-specific flags
- default output format
- machine-readable output shape
- protected human-readable output
- config discovery or config schema
- DB schema, table names, column names, indexes, or schema version handling
- snapshot version or shape
- dry-run/plan output semantics
- Ansible behavior
- destructive-command confirmation behavior

Breaking changes require:

1. a backlog item describing the proposed difference;
2. explicit Russ approval;
3. updated compatibility tests;
4. documentation and migration notes;
5. release notes before any public package release.

## Initial follow-up items

- Extract command-level golden cases from Ruby specs into a Python parity-test manifest.
- Decide whether exact Ruby human-readable wording is required for all progress text or only for documented/spec-protected outputs.
- Decide initial Python version support floor.
- Decide Python database driver defaults for MySQL/MariaDB and PostgreSQL.
