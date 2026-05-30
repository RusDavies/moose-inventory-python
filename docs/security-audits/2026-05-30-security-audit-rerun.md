# Security Audit Rerun — 2026-05-30

Repository: `moose-inventory-python`
Audited commit: `993d224821988d16fb4436ee78cafb76d89c933d`
Audit evidence DB: `.openclaw-security-audit/audit.sqlite` run `2` (local, ignored)
Timestamp: `2026-05-30T08:21:46-04:00`

## Scope

This rerun covers the Python CLI/package implementation after the first audit report was merged. The project exposes local CLI surfaces only: command-line arguments, local YAML configuration, local snapshot import/export files, configured database connections, and local backup/export paths.

## Tooling and evidence

- Repository inventory: 64 files inventoried; manifest detected: `pyproject.toml`.
- Surface inventory recorded: CLI, config YAML parser, snapshot YAML parser, SQLAlchemy database operations, export/backup filesystem writes.
- Semgrep `p/python`: 151 rules, 11 source files scanned, 0 findings, 0 scanner errors.
- `pip-audit .`: 0 known vulnerabilities in resolved project dependencies:
  - `pyyaml` 6.0.3
  - `sqlalchemy` 2.0.50
  - `greenlet` 3.5.1
  - `typing-extensions` 4.15.0
- OSV Scanner 2.3.8: no package lockfile/source results found for this project layout; no vulnerabilities reported. This is expected because the project has `pyproject.toml` but no lockfile.
- Gitleaks 8.30.1: scanned 31 git commits, no leaks found.
- Ruff JSON output: empty.
- Mypy strict: success, no issues in 11 source files.
- Manual grep/review covered secret tokens, command execution, unsafe YAML/pickle/eval, SQL execution, filesystem writes, crypto/hash APIs, subprocess, and network APIs.

## Findings

No evidence-backed P0/P1/P2 vulnerabilities were found.

No secret leaks were found in the working tree or git history by Gitleaks. No known vulnerable resolved Python dependencies were found by `pip-audit`.

## Rechecked security-sensitive paths

- Config loading uses `yaml.safe_load` at `src/moose_inventory/config.py:162`.
- Snapshot import uses `yaml.safe_load` at `src/moose_inventory/cli.py:240`.
- Export writes to caller-supplied local paths at `src/moose_inventory/cli.py:205`.
- SQLite backup writes to caller-supplied local paths at `src/moose_inventory/db.py:476-478`.
- Database URL construction uses SQLAlchemy `URL.create` at `src/moose_inventory/db.py:265-274`.
- Raw SQL execution is limited to static internal index DDL constants at `src/moose_inventory/db.py:378-385`.
- Host/group mutation queries use SQLAlchemy Core predicates rather than string-built SQL.
- Plaintext database passwords remain supported for Ruby compatibility, but `doctor` warns on plaintext config and docs prefer `password_env`.

## Low-risk hardening notes

These remain low-risk in the current local-operator CLI threat model:

1. Export and backup overwrite caller-supplied local paths. If this CLI is wrapped by automation with untrusted path input, add explicit overwrite protection or an allowlist.
2. Config and snapshot YAML files are read whole into memory. `safe_load` avoids object-deserialization execution, but size limits would be useful if third-party snapshots become common.
3. OSV Scanner did not have a lockfile to analyze. For release-grade dependency evidence, add a lockfile or keep using `pip-audit .` in CI against resolved project dependencies.

## Conclusion

The rerun strengthens the previous audit: dependency SCA and git-history secret scanning are now included, and still no actionable vulnerabilities were found. Current security posture is good for a pre-release local system-administration CLI. The next sensible release hardening step is to wire `pip-audit` and `gitleaks` into CI so this does not depend on Skippy remembering to press the correct buttons like a caffeinated raccoon.
