"""Payment settlement records, one per order."""

from __future__ import annotations

import numpy as np
import pandas as pd

from novacart.synthetic import reference
from novacart.synthetic.sampling import draw_index_with_weights


def generate_payments(rng: np.random.Generator, orders: pd.DataFrame) -> pd.DataFrame:
    n = len(orders)
    methods = np.array(list(reference.PAYMENT_METHODS), dtype=object)[
        draw_index_with_weights(rng, list(reference.PAYMENT_METHODS.values()), n)
    ]
    statuses = (
        orders["order_status"].map(reference.PAYMENT_STATUS_BY_ORDER_STATUS).to_numpy()
    )

    order_total = (
        orders["items_subtotal"]
        - orders["discount_amount"]
        + orders["shipping_amount"]
        + orders["tax_amount"]
    ).round(2)
    refunded = np.where(statuses == "refunded", order_total, 0.0)

    settlement_delay = rng.integers(1, 90, size=n)
    paid_at = pd.to_datetime(orders["order_ts"]) + pd.to_timedelta(settlement_delay, unit="m")

    return pd.DataFrame(
        {
            "payment_id": [f"PMT-{i:07d}" for i in range(1, n + 1)],
            "order_id": orders["order_id"].to_numpy(),
            "payment_method": methods.astype(str),
            "payment_status": statuses,
            "amount": order_total.to_numpy(),
            "refunded_amount": np.round(refunded, 2),
            "paid_at": paid_at,
            "provider_reference": [f"PP-{i:010d}" for i in range(1, n + 1)],
        }
    )

