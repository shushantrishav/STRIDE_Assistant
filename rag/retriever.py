# ==========================================
# STRIDE – POLICY RETRIEVER (DETERMINISTIC & BILLING-AWARE)
# ==========================================

import sqlite3
import json
from datetime import date, datetime
from sentence_transformers import SentenceTransformer
from rag.semantic_analyzer import analyze  # your NLP analyzer
from Services.logger_config import logger  # Import logger

# Default DB path
DB_PATH = "stride.db"

# Load embedding model (used only for fallback or future semantic search)
try:
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Embedding model loaded successfully for policy retriever")
except Exception as e:
    logger.error(f"Error loading embedding model: {e}", exc_info=True)
    raise


# ------------------------------------------
# Reject Policy (SYSTEM / NON-DB)
# ------------------------------------------
def reject_policy(reason: str):
    logger.info(f"Policy rejected: {reason}")
    return [{
        "policy_type": "Reject",
        "content": reason,
        "score": 1.0
    }]


# ------------------------------------------
# Fetch policy content helper
# ------------------------------------------
def fetch_policy(policy_type: str, rows):
    for p, content, _ in rows:
        if p == policy_type:
            logger.info(f"Policy fetched: {policy_type}")
            return {
                "policy_type": p,
                "content": content,
                "score": 1.0
            }
    logger.warning(f"Policy type {policy_type} not found. Falling back to default message.")
    return {
        "policy_type": policy_type,
        "content": "Please visit the store for further assistance.",
        "score": 1.0
    }


# ------------------------------------------
# Main Retriever
# ------------------------------------------
def retrieve_policy_chunks(user_text: str, order_data: dict, conn: sqlite3.Connection = None):
    """
    Retrieves the eligible policy for a given user query and order.
    """
    try:
        # Use provided connection or open a new one
        own_conn = False
        if conn is None:
            conn = sqlite3.connect(DB_PATH)
            own_conn = True

        cursor = conn.cursor()
        cursor.execute("SELECT policy_type, content, embedding FROM policy_chunks")
        rows = cursor.fetchall()

        if own_conn:
            conn.close()

        # -------------------------------
        # Calculate days from purchase date
        # -------------------------------
        purchase_date = order_data.get("purchase_date")
        if isinstance(purchase_date, str):
            purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()
        days_used = (date.today() - purchase_date).days

        # -------------------------------
        # NLP analysis (for intent detection)
        # -------------------------------
        analysis = analyze(user_text)
        intent = analysis.get("intent")
        analysis["days_claimed"] = days_used  # override with correct calculation
        logger.info(f"User query analyzed. Intent: {intent}, Days used: {days_used}")

        # -------------------------------
        # HARD REJECTS: Return/Refund/Replacement > 7 days
        # -------------------------------
        if intent in ["refund_request", "return_unused", "replacement_request"] and days_used > 7:
            return reject_policy(f"Request not allowed after {days_used} days. Policy limit is 7 days.")

        if intent == "misuse_or_wear":
            if days_used <= 180:
                return [fetch_policy("Paid_Repair", rows)]
            else:
                return reject_policy("Product shows signs of misuse or wear. Not eligible for free repair.")

        # -------------------------------
        # LOGIC-FIRST ROUTING BASED ON INTENT AND DAYS
        # -------------------------------
        if intent in ["refund_request", "return_unused"] and days_used <= 7:
            return [fetch_policy("Return", rows)]

        if intent == "replacement_request" and days_used <= 7:
            return [fetch_policy("Replacement", rows)]

        if intent in ["manufacturing_defect", "repair_request"]:
            if days_used <= 7:
                return [fetch_policy("Replacement", rows)]
            if 7 < days_used <= 180:
                return [fetch_policy("Repair", rows)]
            if days_used > 180:
                return [fetch_policy("Paid_Repair", rows)]

        # -------------------------------
        # FALLBACK (Inspection Policy)
        # -------------------------------
        return [fetch_policy("Inspection", rows)]

    except Exception as e:
        logger.error(f"Error retrieving policy chunks: {e}", exc_info=True)
        return reject_policy("Internal error while retrieving policy. Please contact support.")
