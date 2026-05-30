# OSV Lockfile Release Evidence — 2026-05-30

Repository: `moose-inventory-python`
Branch: `release/osv-lockfile-evidence`
Version under release preparation: `2.1.0`

## Purpose

The earlier security audit used `pip-audit .` successfully, but OSV Scanner had no lockfile source to analyze from the `pyproject.toml`-only project layout. This evidence pass adds a release lockfile so OSV can scan pinned resolved runtime dependencies.

## Lockfile

Added `requirements-release.txt`, generated with:

```bash
pip-compile --generate-hashes --no-emit-index-url --output-file=requirements-release.txt --strip-extras pyproject.toml
```

The lockfile pins the runtime dependency set and includes package hashes:

- `greenlet==3.5.1`
- `pyyaml==6.0.3`
- `sqlalchemy==2.0.50`
- `typing-extensions==4.15.0`

## OSV Scanner result

Command:

```bash
osv-scanner scan source --recursive --no-ignore --format json --output-file .openclaw-security-audit/raw/osv-release-lock.json .
```

Result:

- OSV Scanner version: `2.3.8`
- Scanned `requirements-release.txt`
- Found 4 packages
- JSON `results`: `[]`
- Exit code: `0`

Conclusion: no known vulnerabilities were reported by OSV for the pinned release dependency set.

## CI gate

Updated GitHub Actions security gates to:

1. Run `pip-audit . --progress-spinner=off`.
2. Install OSV Scanner `2.3.8` from the upstream release asset and verify its SHA-256 digest.
3. Run `osv-scanner scan source --recursive --no-ignore .`.
4. Run Gitleaks across full git history.

## Notes

`--no-ignore` is intentional. Local testing showed OSV Scanner can skip files according to ignore handling in this repository; using `--no-ignore` ensures the committed release lockfile is scanned consistently.
