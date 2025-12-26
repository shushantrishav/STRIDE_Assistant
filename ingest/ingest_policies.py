# ingest_policies.py (upgraded)
from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sentence_transformers import SentenceTransformer

from Services.logger_config import logger

# Ensure Service modules are discoverable (kept from your script)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Services.policy_chunker import split_policies_into_chunks  # noqa: E402


DB_PATH = os.getenv("POLICY_DB_PATH", "stride.db")
POLICY_FILE = os.getenv("POLICY_MD_PATH", "policies/stride_customer_complaint_policies.md")
EMBED_MODEL_NAME = os.getenv("POLICY_EMBED_MODEL", "all-MiniLM-L6-v2")

# If True, wipes and rebuilds table contents (mock/dev friendly).
FULL_REFRESH = os.getenv("POLICY_FULL_REFRESH", "true").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class PolicyChunkRow:
    policy_type: str
    content: Dict[str, Any]
    metadata: Dict[str, Any]
    raw_content: str


def load_embedder() -> SentenceTransformer:
    try:
        model = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info(f"Embedding model loaded: {EMBED_MODEL_NAME}")
        return model
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}", exc_info=True)
        raise


def init_db(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS policy_chunks (
            id TEXT PRIMARY KEY,
            policy_type TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            metadata TEXT NOT NULL,
            embed_model TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_policy_chunks_type ON policy_chunks(policy_type)")
    conn.commit()
    logger.info(f"Database initialized at {DB_PATH}")


def load_chunks() -> List[PolicyChunkRow]:
    chunks = split_policies_into_chunks(POLICY_FILE)
    rows: List[PolicyChunkRow] = []

    for c in chunks:
        rows.append(
            PolicyChunkRow(
                policy_type=str(c.get("policy_type", "Unknown Policy")),
                content=c.get("Content") or {},
                metadata=c.get("metadata") or {},
                raw_content=str(c.get("raw_content", "")),
            )
        )

    logger.info(f"Loaded {len(rows)} policy chunks from markdown: {POLICY_FILE}")
    return rows


def embed_chunks(embedder: SentenceTransformer, rows: List[PolicyChunkRow]) -> List[Dict[str, Any]]:
    """
    Uses batch embedding for speed + consistency.
    Stores embeddings as JSON array in text (keeps compatibility with your retriever). [file:6]
    """
    texts = [r.raw_content for r in rows]
    vectors = embedder.encode(texts, normalize_embeddings=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    out: List[Dict[str, Any]] = []

    for row, vec in zip(rows, vectors):
        out.append(
            {
                "id": uuid4().hex,
                "policy_type": row.policy_type,
                "content": json.dumps(row.content, ensure_ascii=False),
                "embedding": json.dumps(vec.tolist()),
                "metadata": json.dumps(row.metadata, ensure_ascii=False),
                "embed_model": EMBED_MODEL_NAME,
                "created_at": now_iso,
            }
        )

    return out


def write_to_db(conn: sqlite3.Connection, embedded_rows: List[Dict[str, Any]]) -> None:
    cursor = conn.cursor()

    if FULL_REFRESH:
        cursor.execute("DELETE FROM policy_chunks")

    cursor.executemany(
        """
        INSERT INTO policy_chunks (id, policy_type, content, embedding, metadata, embed_model, created_at)
        VALUES (:id, :policy_type, :content, :embedding, :metadata, :embed_model, :created_at)
        """,
        embedded_rows,
    )

    conn.commit()
    logger.info(f"Ingested {len(embedded_rows)} policy chunks into DB.")


def ingest_policies() -> None:
    embedder = load_embedder()
    rows = load_chunks()
    if not rows:
        logger.warning("No policy chunks found; nothing to ingest.")
        return

    embedded_rows = embed_chunks(embedder, rows)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            init_db(conn)
            write_to_db(conn, embedded_rows)
    except Exception as e:
        logger.error(f"Error during ingestion: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    ingest_policies()
