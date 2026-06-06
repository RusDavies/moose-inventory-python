#!/usr/bin/env python3
"""Fail if GitHub Actions workflow uses entries are not immutably pinned."""

from __future__ import annotations

import re
import sys
from pathlib import Path

USES_RE = re.compile(r"^(?P<prefix>\s*uses:\s*)(?P<value>[^#\s]+)")
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DOCKER_DIGEST_RE = re.compile(r"^docker://.+@sha256:[0-9a-fA-F]{64}$")


def workflow_files(root: Path) -> list[Path]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.exists():
        return []
    return sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])


def violations(root: Path) -> list[str]:
    problems: list[str] = []
    for path in workflow_files(root):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            match = USES_RE.match(line)
            if not match:
                continue
            value = match.group("value").strip('"\'')
            if value.startswith("./") or value.startswith(".\\"):
                continue
            if value.startswith("docker://"):
                if not DOCKER_DIGEST_RE.match(value):
                    problems.append(f"{path}:{lineno}: docker action is not pinned by sha256 digest: {value}")
                continue
            if "@" not in value:
                problems.append(f"{path}:{lineno}: remote action missing @<full-sha>: {value}")
                continue
            _action, ref = value.rsplit("@", 1)
            if not FULL_SHA_RE.fullmatch(ref):
                problems.append(f"{path}:{lineno}: remote action is not pinned to a full 40-character SHA: {value}")
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    problems = violations(root)
    if problems:
        print("GitHub Actions pinning check failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print("GitHub Actions pinning check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
