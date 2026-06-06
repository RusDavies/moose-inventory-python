# TODO

Backlog for the Python CLI replacement for the Ruby `moose-inventory` project.

## Open

- [ ] Pin all GitHub Actions workflow `uses:` entries to full 40-character immutable SHAs and add a policy check to prevent moving refs, including PyPI/TestPyPI trusted-publishing workflows.
- [x] Update GitHub Actions dependencies or runner settings for the Node.js 20 deprecation warning before GitHub forces Node.js 24.
- [x] Make version tests derive the expected version from package metadata instead of hard-coding the release number, so patch bumps do not require test literal edits.

## Done

- [x] Configure PyPI/TestPyPI pending trusted publishers and run the first trusted-publishing release.

- [x] Add stronger OSV/lockfile release evidence if public release policy requires lockfile-based scanning.
- [x] Choose the first public Python package version and update package metadata before release.
- [x] Add GitHub Actions CI gates for the release-readiness check, `pip-audit`, and `gitleaks`.
- [x] Run full parity/release gate and record evidence before any public package release.
- [x] Port dry-run and machine-readable plan output for all mutating command families, including `--plan-format` validation.

- [x] Add package/release documentation for PyPI publication, release ownership, artifact integrity/provenance, and vulnerability intake/security patch process.
- [x] Add user documentation for installing the Python CLI, configuring backends, migrating from Ruby, verifying with `doctor`, exporting snapshots before switching, and using Ansible.
- [x] Add MySQL/MariaDB and PostgreSQL backend adapter smoke coverage and document required client dependencies.
- [x] Port the read-only console for human browsing of hosts, groups, tags, and recent audit events.
- [x] Port Ansible dynamic inventory behavior for `--list`, `--host HOSTNAME`, and `--ansible` mode.
- [x] Port append-only audit recording and `audit list` output.
- [x] Port inventory `doctor` checks and formatted report output.
- [x] Port snapshot export/import/preview behavior, preserving additive import semantics and snapshot version/shape.
- [x] Reconcile Ruby/Python child-group cycle behavior: Python now permits cycles to match the current Ruby CLI, with the compatibility decision documented.
- [x] Add development and verification commands for tests, lint, formatting, type checking, coverage, package build, and package metadata validation.
- [x] Port metadata tag commands: `addtag`, `rmtag`, and `listtags`, preserving lowercase/strip/dedupe normalization.
- [x] Port child-group relationship commands: `group addchild` and `group rmchild`, including invalid/circular hierarchy handling and `--delete-orphans` behavior.
- [x] Port host/group variable commands: `addvar`, `rmvar`, and `listvar/listvars` with matching machine-readable output.
- [x] Port host/group association commands: `host addgroup`, `host rmgroup`, `group addhost`, and `group rmhost`, including automatic `ungrouped` behavior.
- [x] Port core group commands: `group add`, `group list`, `group get`, and `group rm` with compatibility tests.
- [x] Port core host commands: `host add`, `host list`, `host get`, and `host rm` with compatibility tests.
- [x] Extract command-level golden cases from Ruby specs into a Python parity-test manifest.
- [x] Build Ruby-vs-Python CLI compatibility harness using disposable SQLite databases and golden/structural output comparisons.
- [x] Port database lifecycle commands: `db status`, `db doctor`, `db migrate`, `db backup FILE`, and `database` alias.
- [x] Implement database schema and migration layer preserving Ruby schema version 4, table names, columns, indexes, and future-schema refusal.
- [x] Implement config discovery and runtime option parsing compatible with the Ruby CLI (`--config`, `--env`, `--format`, `--ansible`, `--trace`, `--list`, `--host`).
- [x] Set up Python CLI package skeleton with `pyproject.toml`, `moose_inventory` package, and `moose-inventory` console entry point.
- [x] Write Ruby parity baseline documentation covering CLI command matrix, global flags, config discovery, DB schema/version, output formats, snapshot shapes, dry-run plan events, and Ansible compatibility. See `docs/compatibility/ruby-parity-baseline.md`.
- [x] Record project tailoring decision: Class 4 + Software CLI Package / Command Package, with Ruby `projects/moose-inventory` as the reference implementation. See `docs/process/tailoring-decision.md`.
