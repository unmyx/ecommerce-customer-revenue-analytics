"""Build the analytical SQL layer: python scripts/build_analytics_layer.py."""

from __future__ import annotations

import sys

from novacart.warehouse import build_main

if __name__ == "__main__":
    sys.exit(build_main())

