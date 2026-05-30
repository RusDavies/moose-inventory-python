"""Command-line entry point for the Python moose-inventory port.

The implementation is intentionally skeletal for now. The Ruby parity baseline in
``docs/compatibility/ruby-parity-baseline.md`` is the behavior contract for future work.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from moose_inventory.config import ConfigError, parse_runtime_options
from moose_inventory.version import __version__

USAGE = """Usage: moose-inventory [GLOBAL FLAGS] COMMAND [ARGS]

Python port skeleton for the Ruby moose-inventory CLI.

Implemented during skeleton setup:
  version   Get the code version
  help      Show this help

Compatibility target:
  See docs/compatibility/ruby-parity-baseline.md
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the moose-inventory CLI."""
    raw_args = list(sys.argv[1:] if argv is None else argv)

    if not raw_args or raw_args[0] in {"help", "--help", "-h"}:
        print(USAGE, end="")
        return 0

    if raw_args[0] == "version":
        print(f"Version {__version__}")
        return 0

    try:
        runtime = parse_runtime_options(raw_args)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not runtime.argv:
        print(USAGE, end="")
        return 0

    command = runtime.argv[0]
    print(
        f"ERROR: command '{command}' is not implemented in the Python port skeleton yet.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
