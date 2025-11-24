# ==========================================
# STRIDE – SEMANTIC ANALYZER
# ==========================================

import re
import numpy as np
from sentence_transformers import SentenceTransformer
from Services.logger_config import logger  # Import logger

# ------------------------------------------
# Load model
# ------------------------------------------
try:
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Semantic analyzer embedding model loaded successfully")
except Exception as e:
    logger.error(f"Error loading semantic analyzer model: {e}", exc_info=True)
    raise

# ------------------------------------------
# Intent definitions
# ------------------------------------------
INTENTS = {
    "manufacturing_defect": [
        "sole separation",
        "shoe broke",
        "stitching failure",
        "glue came off",
        "product defect",
        "material failure",
        "heel detached",
        "shoe cracked",
    ],
    "return_unused": [
        "i want to return this",
        "return this shoe",
        "return my shoe",
        "want to return this shoe",
        "return the product",
        "item not used",
        "changed my mind",
    ],
    "refund_request": [
        "refund request",
        "money back",
        "return for refund",
        "refund eligibility",
    ],
    "repair_request": [
        "repair request",
        "fix the shoe",
        "repair service",
        "need repair",
    ],
    "misuse_or_wear": [
        "normal wear and tear",
        "used heavily",
        "rough usage",
        "worn out",
        "damaged by misuse",
        "accidental damage",
        "old and worn",
        "daily use for years",
    ],
}

# Precompute embeddings
try:
    INTENT_EMBEDDINGS = {intent: embed_model.encode(phrases) for intent, phrases in INTENTS.items()}
    logger.info("Intent embeddings precomputed successfully")
except Exception as e:
    logger.error(f"Error precomputing intent embeddings: {e}", exc_info=True)
    raise


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


# ------------------------------------------
# Extract days
# ------------------------------------------
def extract_days(text: str):
    try:
        match = re.search(r"(\d+)\s*day", text.lower())
        if match:
            return int(match.group(1))
        return None
    except Exception as e:
        logger.warning(f"Failed to extract days from text '{text}': {e}", exc_info=True)
        return None


# ------------------------------------------
# Detect intent
# ------------------------------------------
def detect_intent(text: str):
    try:
        query_vec = embed_model.encode(text)
        best_intent = None
        best_score = 0.0

        for intent, vectors in INTENT_EMBEDDINGS.items():
            for v in vectors:
                score = cosine_similarity(query_vec, v)
                if score > best_score:
                    best_score = score
                    best_intent = intent

        # CONFIDENCE THRESHOLD
        if best_score < 0.35:
            best_intent = None

        logger.info(f"Detected intent: {best_intent}, score: {best_score:.3f}")
        return best_intent, float(best_score)

    except Exception as e:
        logger.error(f"Error detecting intent for text '{text}': {e}", exc_info=True)
        return None, 0.0


# ------------------------------------------
# Analyzer API
# ------------------------------------------
def analyze(user_text: str) -> dict:
    try:
        intent, confidence = detect_intent(user_text)
        days = extract_days(user_text)

        # Explicit reject signal
        reject_signal = False
        if intent == "misuse_or_wear" and confidence >= 0.4:
            reject_signal = True

        result = {
            "intent": intent,
            "intent_confidence": round(confidence, 3),
            "days_claimed": days,
            "reject_signal": reject_signal,
        }

        logger.info(f"Analysis result for text '{user_text}': {result}")
        return result

    except Exception as e:
        logger.error(f"Error analyzing text '{user_text}': {e}", exc_info=True)
        return {
            "intent": None,
            "intent_confidence": 0.0,
            "days_claimed": None,
            "reject_signal": False,
        }
