# ==========================================
# STRIDE – POLICY INGESTION SCRIPT
# ==========================================

import sqlite3
import sys
import os
import json
from datetime import datetime
from sentence_transformers import SentenceTransformer
from Services.logger_config import logger  # Import logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Services.policy_chunker import split_policies_into_chunks

DB_PATH = "stride.db"
POLICY_FILE = "policies/stride_customer_complaint_policies.md"

# ------------------------------------------
# 1️⃣ Load Embedding Model
# ------------------------------------------
try:
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Embedding model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load embedding model: {e}", exc_info=True)
    raise

# ------------------------------------------
# 2️⃣ Initialize DB
# ------------------------------------------
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS policy_chunks (
        id TEXT PRIMARY KEY,
        policy_type TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL
    )
    """)
    logger.info(f"Database initialized at {DB_PATH}")
except Exception as e:
    logger.error(f"Error initializing database at {DB_PATH}: {e}", exc_info=True)
    raise

# ------------------------------------------
# 3️⃣ Generate 6-char IDs
# ------------------------------------------
def gen_id():
    import random, string
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ------------------------------------------
# 4️⃣ Ingest Policies
# ------------------------------------------
try:
    chunks = split_policies_into_chunks(POLICY_FILE)
    for chunk in chunks:
        embedding = embed_model.encode(chunk["content"]).tolist()
        cursor.execute("""
        INSERT INTO policy_chunks (id, policy_type, content, embedding, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            gen_id(),
            chunk["policy_type"],
            chunk["content"],
            json.dumps(embedding),
            datetime.utcnow()
        ))
    conn.commit()
    logger.info(f"Ingested {len(chunks)} policy chunks successfully from {POLICY_FILE}")
except Exception as e:
    logger.error(f"Error ingesting policies from {POLICY_FILE}: {e}", exc_info=True)
finally:
    conn.close()
    logger.info("Database connection closed")
