"""Load generated CSVs into PostgreSQL: python scripts/load_raw.py."""

from __future__ import annotations

import sys

from novacart.ingestion.cli import main

if __name__ == "__main__":
    sys.exit(main())

