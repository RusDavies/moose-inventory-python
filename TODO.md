# TODO

Backlog for the Python CLI replacement for the Ruby `moose-inventory` project.

## Open

- [ ] Record project tailoring decision: Class 4 + Software CLI Package / Command Package, with Ruby `projects/moose-inventory` as the reference implementation.
- [ ] Write Ruby parity baseline documentation covering CLI command matrix, global flags, config discovery, DB schema/version, output formats, snapshot shapes, dry-run plan events, and Ansible compatibility.
- [ ] Set up Python CLI package skeleton with `pyproject.toml`, `moose_inventory` package, and `moose-inventory` console entry point.
- [ ] Add development and verification commands for tests, lint, formatting, type checking, coverage, package build, and package metadata validation.
- [ ] Implement config discovery and runtime option parsing compatible with the Ruby CLI (`--config`, `--env`, `--format`, `--ansible`, `--trace`, `--list`, `--host`).
- [ ] Implement database schema and migration layer preserving Ruby schema version 4, table names, columns, indexes, and future-schema refusal.
- [ ] Build Ruby-vs-Python CLI compatibility harness using disposable SQLite databases and golden/structural output comparisons.
- [ ] Port database lifecycle commands: `db status`, `db doctor`, `db migrate`, `db backup FILE`, and `database` alias.
- [ ] Port core host commands: `host add`, `host list`, `host get`, and `host rm` with compatibility tests.
- [ ] Port core group commands: `group add`, `group list`, `group get`, and `group rm` with compatibility tests.
- [ ] Port host/group association commands: `host addgroup`, `host rmgroup`, `group addhost`, and `group rmhost`, including automatic `ungrouped` behavior.
- [ ] Port host/group variable commands: `addvar`, `rmvar`, and `listvar/listvars` with matching machine-readable output.
- [ ] Port child-group relationship commands: `group addchild` and `group rmchild`, including invalid/circular hierarchy handling and `--delete-orphans` behavior.
- [ ] Port metadata tag commands: `addtag`, `rmtag`, and `listtags`, preserving lowercase/strip/dedupe normalization.
- [ ] Port dry-run and machine-readable plan output for all mutating command families, including `--plan-format` validation.
- [ ] Port snapshot export/import/preview behavior, preserving additive import semantics and snapshot version/shape.
- [ ] Port inventory `doctor` checks and formatted report output.
- [ ] Port append-only audit recording and `audit list` output.
- [ ] Port Ansible dynamic inventory behavior for `--list`, `--host HOSTNAME`, and `--ansible` mode.
- [ ] Port the read-only console or explicitly document any compatibility decision before deferring it.
- [ ] Add MySQL/MariaDB and PostgreSQL backend adapter smoke coverage and document required client dependencies.
- [ ] Add user documentation for installing the Python CLI, configuring backends, migrating from Ruby, verifying with `doctor`, exporting snapshots before switching, and using Ansible.
- [ ] Add package/release documentation for PyPI publication, release ownership, artifact integrity/provenance, and vulnerability intake/security patch process.
- [ ] Run full parity/release gate and record evidence before any public package release.

## Done

_No completed items yet._
