# Security Audit — 2026-05-30

Repository: `moose-inventory-python`
Audited commit: `c276d1280b977a533d1a4e3555bdfa93286b63af`
Audit evidence DB: `.openclaw-security-audit/audit.sqlite` run `1` (local, ignored)

## Scope

This audit reviewed the Python CLI/package implementation, tests, packaging metadata, and release documentation. The repo has no HTTP service, daemon, webhook, or public network listener; reachable surfaces are local CLI commands, local YAML config/snapshot files, configured database connections, and local filesystem paths supplied by the invoking user.

## Tooling and evidence

- Repository/symbol inventory: 55 files inventoried, 16 Python files scanned for symbols, 238 symbols recorded.
- Surface inventory recorded: CLI, config YAML parser, snapshot YAML parser, SQLAlchemy database operations, export/backup filesystem writes.
- Semgrep `p/python`: 151 Python rules, 11 source files scanned, 0 findings.
- Ruff: 0 findings.
- Mypy strict: success, no issues in 11 source files.
- Grep review covered secret tokens, command execution, unsafe YAML/pickle/eval, filesystem writes, SQL execution, crypto/hash APIs, and network APIs.
- Previous project gate at this commit: `./scripts/check.sh` passed with 137 tests, Ruff, mypy, build, and twine check.

Dependency SCA limitation: `pip-audit`, `safety`, `osv-scanner`, `bandit`, `gitleaks`, and `trufflehog` were not installed in this environment. No lockfile is present, so dependency vulnerability status should be rechecked in CI/release tooling with an SCA scanner before public release.

## Findings

No evidence-backed P0/P1/P2 vulnerabilities were found.

I did not find reachable command execution, unsafe deserialization, SQL injection, credential leaks, network SSRF surface, authentication/authorization flaws, or dangerous crypto use in the audited code.

## Hardening notes / low-risk observations

These are not being reported as exploitable vulnerabilities in the current local-CLI threat model, but they are worth tracking before a public release.

### H1 — Filesystem writes intentionally overwrite caller-supplied paths

Evidence:

- `src/moose_inventory/cli.py:205` writes export output to `Path(args[0]).write_text(...)`.
- `src/moose_inventory/db.py:476-478` resolves the backup destination, creates parent directories, and writes bytes with `destination.write_bytes(...)`.
- `src/moose_inventory/db.py:243-245` resolves the configured SQLite file path, creates parent directories, and opens/creates the database.

Assessment: local CLI user controls these paths, so this is expected behavior rather than a privilege-boundary bypass. If the CLI is ever wrapped by automation that accepts untrusted path input, add overwrite protection, destination allowlists, or explicit `--force` behavior for backup/export paths.

### H2 — Snapshot import reads whole YAML files into memory

Evidence:

- `src/moose_inventory/cli.py:240` loads the full snapshot with `Path(file_name).read_text(...)` followed by `yaml.safe_load(...)`.
- `src/moose_inventory/config.py:162` does the same for configuration files.

Assessment: `yaml.safe_load` avoids Python object deserialization, so I did not find unsafe YAML execution. Very large local files can still consume memory/CPU. That is low risk for an operator-run CLI, but if snapshots may come from untrusted sources, consider file-size limits and clearer import guidance.

### H3 — Plaintext database password remains supported for Ruby compatibility

Evidence:

- `src/moose_inventory/db.py:286-304` supports either `password` or `password_env`.
- `src/moose_inventory/doctor.py:56-70` warns when plaintext `password` is present.
- `docs/backend-adapters.md` recommends `password_env`.

Assessment: this is documented compatibility behavior and has a doctor warning. Keep the warning; prefer `password_env` in examples and release notes.

## Positive security properties observed

- YAML parsing uses `yaml.safe_load`, not unsafe `yaml.load`.
- SQL operations use SQLAlchemy Core expressions and fixed schema constants; the only `exec_driver_sql` path builds index DDL from static internal constants (`src/moose_inventory/db.py:378-385`).
- Network database URLs are constructed with `URL.create`, which handles credential quoting (`src/moose_inventory/db.py:265-274`).
- Dry-run commands avoid audit writes via `infer_audit_metadata` returning `None` when `--dry-run` is present.
- Destructive host/group operations require `--yes` unless running `--dry-run`.
- `doctor` detects plaintext DB passwords and inventory integrity issues.

## Recommended follow-up before public release

1. Add CI SCA tooling, preferably `pip-audit` or `osv-scanner`, and fail releases on known vulnerable direct/runtime dependencies.
2. Add a secret scanner in CI (`gitleaks` or equivalent) before release tags.
3. Consider overwrite protection for backup/export destinations if the CLI may be run by automation with untrusted path arguments.
4. Consider snapshot/config file-size guidance or limits if operators are expected to import third-party snapshots.

## Conclusion

Current security posture is good for a local system-administration CLI in pre-release state. I found no high-confidence actionable vulnerabilities, but the release process should still add dependency and secret scanning before publishing because Python packaging without SCA is just vibes wearing a trench coat.
