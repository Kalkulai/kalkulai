from __future__ import annotations

import sys

from . import catalog_cli


def main() -> int:
    return catalog_cli.main()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
