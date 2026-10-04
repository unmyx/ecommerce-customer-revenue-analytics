"""Reconcile analytics against raw: python scripts/run_reconciliation.py."""

from __future__ import annotations

import sys

from novacart.warehouse import reconcile_main

if __name__ == "__main__":
    sys.exit(reconcile_main())

