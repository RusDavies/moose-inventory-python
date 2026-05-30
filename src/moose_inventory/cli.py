"""Command-line entry point for the Python moose-inventory port.

The implementation is intentionally skeletal for now. The Ruby parity baseline in
``docs/compatibility/ruby-parity-baseline.md`` is the behavior contract for future work.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

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
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in {"help", "--help", "-h"}:
        print(USAGE, end="")
        return 0

    if args[0] == "version":
        print(f"Version {__version__}")
        return 0

    print(
        f"ERROR: command '{args[0]}' is not implemented in the Python port skeleton yet.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
