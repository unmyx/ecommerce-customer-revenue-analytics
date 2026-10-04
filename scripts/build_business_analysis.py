"""Run the business analysis and write tables + figures.

    python scripts/build_business_analysis.py
"""

from __future__ import annotations

import sys

from novacart.analytics.report import main

if __name__ == "__main__":
    sys.exit(main())

