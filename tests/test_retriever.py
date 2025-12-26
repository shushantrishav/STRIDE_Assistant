# tests/test_retriever.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import date, timedelta

import pytest

import rag.retriever as retriever


@pytest.fixture
def temp_db(tmp_path: Path) -> str:
    db_path = tmp_path / "stride.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE policy_chunks (
            id TEXT PRIMARY KEY,
            policy_type TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            metadata TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        INSERT INTO policy_chunks (id, policy_type, content, embedding, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "A1",
            "Return Policy",
            json.dumps({"Eligibility": ["x"], "Ineligible": [], "Resolution": []}),
            json.dumps([1.0, 0.0, 0.0]),
            json.dumps({"min_days": 0, "max_days": 7, "eligible_intents": ["return_request"]}),
            "now",
        ),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_retrieve_policy_selects_best_match(monkeypatch, temp_db: str):
    # Mock embed + similarity for determinism. [file:6]
    monkeypatch.setattr(retriever, "embed_text", lambda _: [1.0, 0.0, 0.0])
    monkeypatch.setattr(retriever, "cosine_similarity", lambda a, b: 0.9)

    order = {"purchase_date": (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")}
    result = retriever.retrieve_policy(
        user_query="i want return",
        predicted_intent="return_request",
        order_data=order,
        db_path=temp_db,      # requires your upgraded signature
    )
    assert result is not None
    assert result["policy_type"] == "Return Policy"
    assert result["match_score"] == 0.9
