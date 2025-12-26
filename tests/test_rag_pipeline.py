# tests/test_rag_pipeline.py
from __future__ import annotations

from datetime import date, timedelta

import pytest

import Services.rag_pipeline as rag_pipeline


@pytest.fixture
def order_stub() -> dict:
    return {
        "order_id": "ORD123",
        "purchase_date": (date.today() - timedelta(days=2)).strftime("%Y-%m-%d"),
        "outlet_id": "OUT1",
        "product_id": "P1",
        "size": "9",
        "customer_phone": "9999999999",
        "full_name": "Test User",
    }


def test_general_chat_two_consecutive_closes(monkeypatch, order_stub):
    monkeypatch.setattr(rag_pipeline, "get_order_from_cache", lambda _oid: order_stub)

    class FakeAnalyser:
        def analyse(self, _txt):
            return {"intent": "general_chat"}

    monkeypatch.setattr(rag_pipeline, "StrideIntentAnalyser", FakeAnalyser)

    p = rag_pipeline.STRIDERAGPipeline(order_id="ORD123")

    r1 = p.process_turn("hi")
    assert r1["final_ticket"] == "GCD"
    assert r1["chat_closed"] is False

    r2 = p.process_turn("hello again")
    assert r2["final_ticket"] == "GCD"
    assert r2["chat_closed"] is True


def test_turn1_returns_clarification_T1(monkeypatch, order_stub):
    monkeypatch.setattr(rag_pipeline, "get_order_from_cache", lambda _oid: order_stub)

    class FakeAnalyser:
        def analyse(self, _txt):
            return {
                "intent": "repair_request",
                "primary_intent": "repair_request",
                "misuse_or_accident": False,
            }

    monkeypatch.setattr(rag_pipeline, "StrideIntentAnalyser", FakeAnalyser)

    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_policy",
        lambda **kwargs: {"policy_type": "Repair", "content": {}, "match_score": 0.9},
    )

    monkeypatch.setattr(rag_pipeline, "prefetch_inventory", lambda *args, **kwargs: None)
    monkeypatch.setattr(rag_pipeline, "is_inventory_available", lambda *args, **kwargs: True)

    class FakeEngine:
        def make_decision(self, **kwargs):
            # Pipeline uppercases this into the signal it stores. [file:13]
            return {"ticket_type": "REPAIR", "reason": "ok", "decision": "approve"}

    monkeypatch.setattr(rag_pipeline, "StrideDecisionEngine", FakeEngine)

    class FakePromptBuilder:
        def __init__(self, *_args, **_kwargs): ...
        def build_final_prompt(self, **_kwargs):
            return "PROMPT"

    monkeypatch.setattr(rag_pipeline, "StridePromptBuilder", FakePromptBuilder)

    p = rag_pipeline.STRIDERAGPipeline(order_id="ORD123")
    r = p.process_turn("shoe sole came off")

    assert r["final_ticket"] == "T1"
    assert r["needs_clarification"] is True
    assert r["ai_message"] == "PROMPT"
    assert r["turn_count"] == 1

    # Signals are now structured objects (PipelineSignal). Validate fields instead of raw list compare.
    assert len(p.signals) == 2
    assert p.signals[0].source == "retriever"
    assert p.signals[0].value.value == "REPAIR"
    assert p.signals[0].turn == 1
    assert p.signals[0].confidence == 0.9

    assert p.signals[1].source == "engine"
    assert p.signals[1].value.value == "REPAIR"
    assert p.signals[1].turn == 1


def test_inventory_override_replacement_to_inspection(monkeypatch, order_stub):
    monkeypatch.setattr(rag_pipeline, "get_order_from_cache", lambda _oid: order_stub)

    class FakeAnalyser:
        def analyse(self, _txt):
            return {
                "intent": "replacement_request",
                "primary_intent": "replacement_request",
                "misuse_or_accident": False,
            }

    monkeypatch.setattr(rag_pipeline, "StrideIntentAnalyser", FakeAnalyser)

    monkeypatch.setattr(
        rag_pipeline,
        "retrieve_policy",
        lambda **kwargs: {"policy_type": "Replacement", "content": {}, "match_score": 0.9},
    )

    monkeypatch.setattr(rag_pipeline, "prefetch_inventory", lambda *args, **kwargs: None)
    monkeypatch.setattr(rag_pipeline, "is_inventory_available", lambda *args, **kwargs: False)

    class FakeEngine:
        def make_decision(self, **kwargs):
            return {"ticket_type": "REPLACEMENT", "reason": "ok", "decision": "approve"}

    monkeypatch.setattr(rag_pipeline, "StrideDecisionEngine", FakeEngine)

    class FakePromptBuilder:
        def __init__(self, *_args, **_kwargs): ...
        def build_final_prompt(self, **_kwargs):
            return "PROMPT"

    monkeypatch.setattr(rag_pipeline, "StridePromptBuilder", FakePromptBuilder)

    p = rag_pipeline.STRIDERAGPipeline(order_id="ORD123")

    # Turn 1: clarification stage
    p.process_turn("need replacement")

    # Turn 2: arbitration happens; override should apply when inventory is unavailable. [file:13]
    r2 = p.process_turn("it arrived damaged")
    assert r2["final_ticket"] == "INSPECTION"
