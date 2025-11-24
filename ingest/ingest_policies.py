# ==============================================================================
# STRIDE – POLICY INGESTION SCRIPT (UPDATED)
# ==============================================================================

import sqlite3
import sys
import os
import json
import random
import string
from datetime import datetime
from sentence_transformers import SentenceTransformer
from Services.logger_config import logger

# Ensure Service modules are discoverable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Services.policy_chunker import split_policies_into_chunks

DB_PATH = "stride.db"
POLICY_FILE = "policies/stride_customer_complaint_policies.md"

# ------------------------------------------
# 1️⃣ Load Embedding Model
# ------------------------------------------
try:
    # all-MiniLM-L6-v2 is efficient for text-based policy retrieval
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Embedding model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load embedding model: {e}", exc_info=True)
    raise

# ------------------------------------------
# 2️⃣ Initialize Database
# ------------------------------------------
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # content stores the structured JSON string
        # metadata stores the min/max days and intents
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS policy_chunks (
            id TEXT PRIMARY KEY,
            policy_type TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            metadata TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
        """)
        conn.commit()
        logger.info(f"Database initialized at {DB_PATH}")
        return conn
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        raise

# ------------------------------------------
# 3️⃣ Utility: Generate Unique ID
# ------------------------------------------
def gen_id():
    """Generates a 6-character alphanumeric ID."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ------------------------------------------
# 4️⃣ Ingestion Logic
# ------------------------------------------
def ingest_policies():
    conn = init_db()
    cursor = conn.cursor()

    try:
        # Clear existing policies to avoid duplicates during re-ingestion
        cursor.execute("DELETE FROM policy_chunks")
        
        chunks = split_policies_into_chunks(POLICY_FILE)
        
        for chunk in chunks:
            # We embed the 'raw_content' for better semantic search accuracy
            embedding = embed_model.encode(chunk["raw_content"]).tolist()
            
            # Serialize the structured lists (Eligibility, Ineligible, etc.)
            content_json = json.dumps(chunk["Content"])
            
            # Serialize the automation metadata (min_days, max_days, intents)
            metadata_json = json.dumps(chunk["metadata"])

            cursor.execute("""
            INSERT INTO policy_chunks (id, policy_type, content, embedding, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                gen_id(),
                chunk["policy_type"],
                content_json,
                json.dumps(embedding),
                metadata_json,
                datetime.utcnow()
            ))

        conn.commit()
        logger.info(f"Ingested {len(chunks)} structured policy chunks successfully.")

    except Exception as e:
        logger.error(f"Error during ingestion: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    ingest_policies()