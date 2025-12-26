# tests/test_decision_engine.py
from __future__ import annotations

from datetime import date, timedelta

import pytest

from rag.decision_engine import StrideDecisionEngine


def _order_with_days(days_used: int) -> dict:
    return {
        "order_id": "ORDX",
        "purchase_date": (date.today() - timedelta(days=days_used)).strftime("%Y-%m-%d"),
    }


@pytest.mark.parametrize(
    "primary_intent, expected_ticket, expected_decision",
    [
        ("general_chat", "REJECT", "reject"),
        ("refund_request", "RETURN", "manual"),
        ("return_request", "RETURN", "manual"),
    ],
)
def test_engine_basic_intents(primary_intent, expected_ticket, expected_decision):
    engine = StrideDecisionEngine()
    result = engine.make_decision(
        order_data=_order_with_days(2),
        inventory_available=True,
        turn_count=1,
        analysis={"primary_intent": primary_intent, "misuse_or_accident": False},
    )
    assert result["ticket_type"] == expected_ticket
    assert result["decision"] == expected_decision


def test_refund_reject_after_7_days():
    engine = StrideDecisionEngine()
    result = engine.make_decision(
        order_data=_order_with_days(8),
        inventory_available=True,
        turn_count=1,
        analysis={"primary_intent": "refund_request", "misuse_or_accident": False},
    )
    assert result["ticket_type"] == "REJECT"
    assert result["decision"] == "reject"
    assert result["generate_ticket"] is False


def test_misuse_in_warranty_becomes_paid_repair():
    engine = StrideDecisionEngine()
    result = engine.make_decision(
        order_data=_order_with_days(10),
        inventory_available=True,
        turn_count=1,
        analysis={"primary_intent": "repair_request", "misuse_or_accident": True},
    )
    assert result["ticket_type"] == "PAID_REPAIR"
    assert result["paid_service_flag"] is True


def test_replacement_with_stock_within_7_days():
    engine = StrideDecisionEngine()
    result = engine.make_decision(
        order_data=_order_with_days(3),
        inventory_available=True,
        turn_count=1,
        analysis={"primary_intent": "replacement_request", "misuse_or_accident": False},
    )
    assert result["ticket_type"] == "REPLACEMENT"
    assert result["decision"] == "approve"


def test_replacement_stockout_within_7_days_goes_inspection():
    engine = StrideDecisionEngine()
    result = engine.make_decision(
        order_data=_order_with_days(3),
        inventory_available=False,
        turn_count=1,
        analysis={"primary_intent": "replacement_request", "misuse_or_accident": False},
    )
    assert result["ticket_type"] == "INSPECTION"
    assert result["decision"] == "manual"


def test_turn_limit_escalation():
    engine = StrideDecisionEngine()
    result = engine.make_decision(
        order_data=_order_with_days(3),
        inventory_available=True,
        turn_count=3,
        analysis={"primary_intent": "repair_request", "misuse_or_accident": False},
    )
    assert result["ticket_type"] == "INSPECTION"
    assert result["decision"] == "manual"
