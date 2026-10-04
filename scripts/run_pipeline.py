"""Run the complete pipeline: python scripts/run_pipeline.py [--with-tests]."""

from __future__ import annotations

import sys

from novacart.pipeline import main

if __name__ == "__main__":
    sys.exit(main())

