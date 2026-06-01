# Release and Package Operations

This project publishes a Python command package whose compatibility contract is the `moose-inventory` CLI. Treat releases as operator-impacting even though this is not a hosted service.

## Ownership

- Package owner: Russ Davies / `RusDavies` project namespace.
- Release branch source: `master` after all feature branches have been merged.
- Ruby reference: sibling `projects/moose-inventory`; parity tests must pass when Ruby is available.

## Pre-release gate

Run the full local gate from a clean tree:

```bash
git status --short
./scripts/check.sh
```

The gate runs:

1. `pytest`
2. `ruff check src tests`
3. `mypy`
4. package build
5. `twine check dist/*`

Before a public release, also run any available real-backend smoke checks for MySQL/MariaDB and PostgreSQL, because the default test suite only instantiates network database URLs and does not open service connections.

## Artifact integrity

Build artifacts are created under `dist/` and should be regenerated for each release:

```bash
rm -rf dist build *.egg-info
python -m build
python -m twine check dist/*
sha256sum dist/*
```

Record the exact git commit, package version, filenames, and SHA-256 hashes in release notes. Do not publish artifacts built from a dirty tree. The robots have enough ways to embarrass us without handing them that one.

## PyPI publication

Publication uses PyPI Trusted Publishing from GitHub Actions. Do not use local `twine upload` for normal releases, and do not store PyPI tokens in the repository.

The workflow is `.github/workflows/publish.yml`. It is manually triggered with:

- `target`: `testpypi` or `pypi`
- `version`: the expected package version, which must match both `pyproject.toml` and `src/moose_inventory/version.py`

The workflow rebuilds the distributions, runs the release-readiness gate, dependency/security scanners, `twine check`, records artifact hashes in the job log, then publishes using OIDC via `pypa/gh-action-pypi-publish`.

Trusted publisher setup required on PyPI/TestPyPI:

- Owner/account: `RusDavies`
- Repository: `RusDavies/moose-inventory-python`
- Workflow: `publish.yml`
- Environment: `testpypi` for TestPyPI and `pypi` for PyPI
- Project/distribution name: `moose-inventory`

For the first release, create a pending trusted publisher on PyPI/TestPyPI before running the workflow. Keep the GitHub `pypi` environment protected with required reviewer approval so real publication remains a deliberate human action.

Never commit PyPI tokens, `.pypirc`, generated credentials, database passwords, or local config files.

## Versioning

Python package versions track the Ruby compatibility line for major/minor versions, while Python patch releases are independent. For example, Python `2.1.x` means the Python CLI targets the Ruby `2.1` behavior contract; Python-only fixes can ship as `2.1.1`, `2.1.2`, and so on. When the Ruby reference advances to `2.2`, the Python package should move to `2.2.0` once parity with that line is verified.

The first public Python release version is `2.1.0`, matching the Ruby `2.1` compatibility target.

Before first public release:

1. Confirm `pyproject.toml` and `src/moose_inventory/version.py` carry the intended release version.
2. Update docs/examples if the package name or extras change.
3. Regenerate `requirements-release.txt` with `pip-compile --generate-hashes --no-emit-index-url --output-file=requirements-release.txt --strip-extras pyproject.toml` when runtime dependencies change.
4. Run the full gate.
5. Ensure PyPI/TestPyPI trusted publishers and GitHub environments exist.
6. Trigger the publish workflow for `testpypi` and verify installation/import from TestPyPI.
7. Trigger the publish workflow for `pypi` after human approval.
8. Tag the release after the final verification/publication commit when appropriate.

## Vulnerability intake and security patches

Until a formal security advisory process exists, use the GitHub repository security advisory flow or private maintainer contact for vulnerability reports. Security fixes should:

1. Reproduce or characterize the issue privately.
2. Add regression tests when safe.
3. Patch with the smallest compatible change.
4. Run the full gate.
5. Publish a fixed package and advisory notes if public users may be affected.

For dependency vulnerabilities, update the affected dependency bounds only after checking compatibility with the CLI, schema, and package build gates.

## Release evidence packet

Keep release evidence in `docs/release-evidence/` or equivalent release notes:

- Commit SHA and branch.
- `./scripts/check.sh` output summary.
- Ruby/Python parity status.
- Package filenames and SHA-256 hashes.
- Backend smoke evidence, including any skipped real-service checks.
- Dependency/security scanner output, including `pip-audit`, OSV Scanner against `requirements-release.txt`, and Gitleaks.
- Known limitations or compatibility exceptions.
