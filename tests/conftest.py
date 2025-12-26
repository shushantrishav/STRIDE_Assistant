# tests/conftest.py
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, timedelta

import pytest


# Make repo root importable so `Services.*`, `rag.*`, `cache.*` work in tests. [file:13]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def today() -> date:
    return date.today()


@pytest.fixture
def order_base(today: date) -> dict:
    # Keep fields consistent with your codebase (order_id, purchase_date, outlet_id, product_id, size). [file:13]
    return {
        "order_id": "ORD123",
        "purchase_date": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        "outlet_id": "OUT1",
        "product_id": "P1",
        "size": "9",
        "customer_phone": "9999999999",
        "full_name": "Test User",
    }
