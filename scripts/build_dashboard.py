"""Build the dashboard datasets, executive summary and page previews.

    python scripts/build_dashboard.py
"""

from __future__ import annotations

import sys

from novacart.dashboard.cli import main

if __name__ == "__main__":
    sys.exit(main())

