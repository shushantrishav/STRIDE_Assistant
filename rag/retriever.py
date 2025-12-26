# retriever.py (upgraded: clean SRP helpers, safer parsing, context manager, optional limits)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import json
import sqlite3

from Services.embedder import embed_text, cosine_similarity
from Services.logger_config import logger


DB_PATH = "stride.db"


@dataclass(frozen=True)
class RetrievedPolicy:
    policy_type: str
    content: Any
    match_score: float
    metadata: Dict[str, Any]


# -----------------------------
# Utilities
# -----------------------------
def _parse_purchase_date(order_data: Dict[str, Any]) -> Optional[date]:
    raw = order_data.get("purchase_date")
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def _days_used(order_data: Dict[str, Any]) -> Optional[int]:
    purchase_date = _parse_purchase_date(order_data)
    if purchase_date is None:
        return None
    return (date.today() - purchase_date).days


def _load_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _fetch_policy_rows(db_path: str) -> List[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT policy_type, content, embedding, metadata FROM policy_chunks")
        return cursor.fetchall()


def _is_eligible(meta: Dict[str, Any], days_used: int, predicted_intent: str) -> bool:
    min_days = int(meta.get("min_days", 0) or 0)
    max_days = meta.get("max_days")
    max_days = int(max_days) if isinstance(max_days, int) else (999999 if max_days is None else int(max_days))

    eligible_intents = meta.get("eligible_intents") or []
    if not isinstance(eligible_intents, list):
        eligible_intents = []

    return (min_days <= days_used <= max_days) and (predicted_intent in eligible_intents)


# -----------------------------
# Public API
# -----------------------------
def retrieve_policy(
    user_query: str,
    predicted_intent: str,
    order_data: Dict[str, Any],
    db_path: str = DB_PATH,
    min_match_score: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """
    Returns the best policy match (dict compatible with your pipeline), or None.

    Output shape:
      {"policy_type": str, "content": Any, "match_score": float, "metadata": dict}
    """
    days = _days_used(order_data)
    if days is None:
        logger.warning("retrieve_policy: missing/invalid purchase_date; cannot apply day-bounds filter.")
        return None

    logger.info(f"retrieve_policy: days_used={days}, predicted_intent={predicted_intent}")

    query_vec = embed_text(user_query)
    if not query_vec:
        logger.warning("retrieve_policy: embedding failed; returning None")
        return None

    rows = _fetch_policy_rows(db_path)

    best: Optional[RetrievedPolicy] = None

    for row in rows:
        meta = _load_json(row["metadata"], default={})
        if not isinstance(meta, dict):
            meta = {}

        if not _is_eligible(meta, days, predicted_intent):
            continue

        embedding = _load_json(row["embedding"], default=None)
        if embedding is None:
            continue

        score = cosine_similarity(query_vec, embedding)
        if score < min_match_score:
            continue

        candidate = RetrievedPolicy(
            policy_type=str(row["policy_type"]),
            content=_load_json(row["content"], default=row["content"]),
            match_score=float(score),
            metadata=meta,
        )

        if best is None or candidate.match_score > best.match_score:
            best = candidate

    if best is None:
        return None

    return {
        "policy_type": best.policy_type,
        "content": best.content,
        "match_score": best.match_score,
        "metadata": best.metadata,
    }
