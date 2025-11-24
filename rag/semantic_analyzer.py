# ==========================================
# STRIDE – DYNAMIC INTENT + SIGNAL + CATEGORY ANALYZER
# ==========================================

import re
import json
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from Services.logger_config import logger

# ------------------------------------------
# Load embedding model
# ------------------------------------------
try:
    embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Stride embedding model loaded successfully")
except Exception as e:
    logger.error(f"Embedding model load failed: {e}", exc_info=True)
    raise

# ------------------------------------------
# Load configuration
# ------------------------------------------
CONFIG_PATH = Path("config/analyzer_config.json")

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)

    INTENTS = CONFIG.get("intents", {})
    SIGNALS = CONFIG.get("signals", {})

    logger.info("Analyzer configuration loaded")
except Exception as e:
    logger.error(f"Failed to load config: {e}", exc_info=True)
    raise

# ------------------------------------------
# Precompute embeddings
# ------------------------------------------
try:
    INTENT_EMBEDDINGS = {
        intent: embed_model.encode(phrases)
        for intent, phrases in INTENTS.items()
    }

    SIGNAL_EMBEDDINGS = {
        signal: embed_model.encode(phrases)
        for signal, phrases in SIGNALS.items()
    }

    logger.info("Intent and signal embeddings computed")
except Exception as e:
    logger.error(f"Embedding computation failed: {e}", exc_info=True)
    raise

# ------------------------------------------
# Utilities
# ------------------------------------------
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def extract_days(text: str):
    match = re.search(r"(\d+)\s*(day|days)", text.lower())
    return int(match.group(1)) if match else None


# ------------------------------------------
# Intent detection
# ------------------------------------------
def detect_intent(text: str, threshold: float = 0.35):
    query_vec = embed_model.encode(text)

    best_intent = "anything"
    best_score = 0.0

    for intent, vectors in INTENT_EMBEDDINGS.items():
        for v in vectors:
            score = cosine_similarity(query_vec, v)
            if score > best_score:
                best_score = score
                best_intent = intent

    if best_score < threshold:
        return "inspection_request", float(best_score)

    return best_intent, float(best_score)


# ------------------------------------------
# Signal detection
# ------------------------------------------
def detect_signals(text: str):
    query_vec = embed_model.encode(text)

    detected = {
        "manufacturing_defect": False,
        "misuse_or_wear": False,
        "intentional_damage": False,
    }

    thresholds = {
        "manufacturing_defect": 0.55,
        "misuse_or_wear": 0.50,
        "intentional_damage": 0.65,
    }

    priority = [
        "manufacturing_defect",
        "intentional_damage",
        "misuse_or_wear",
    ]

    for signal in priority:
        for v in SIGNAL_EMBEDDINGS.get(signal, []):
            if cosine_similarity(query_vec, v) >= thresholds[signal]:
                detected[signal] = True
                return detected

    return detected


# ------------------------------------------
# Category determination (FIXED)
# ------------------------------------------
def categorize_request(intent: str, signals: dict, confidence: float):
    """
    Final business categorization layer.
    Intents are preserved.
    Signals only decide cost responsibility.
    """
    DOMAIN_CONFIDENCE_THRESHOLD = 0.30

    # 🚫 0️⃣ Completely unrelated / unknown
    if confidence < DOMAIN_CONFIDENCE_THRESHOLD:
        return "unknown_request"

    # Paid repair has highest priority
    if (
        intent == "paid_repair_request"
        or signals.get("intentional_damage")
        or signals.get("misuse_or_wear")
    ):
        return "paid_repair_request"

    # Return / refund
    if intent in {"return_request", "refund_request"}:
        return "return_refund_request"

    # Manufacturing defect → free repair / replacement
    if signals.get("manufacturing_defect"):
        return "replacement_repair_request"

    # Any repair / replacement intent defaults to free evaluation
    if intent in {"repair_request", "replacement_request"}:
        return "replacement_repair_request"

    # Low confidence or unclear
    if confidence < 0.35 or intent in {"inspection_request", "anything"}:
        return "inspection_request"

    return "inspection_request"


# ------------------------------------------
# Public Analyzer API
# ------------------------------------------
def analyze(user_text: str) -> dict:
    try:
        intent, confidence = detect_intent(user_text)
        days_claimed = extract_days(user_text)
        signals = detect_signals(user_text)
        category = categorize_request(intent, signals, confidence)

        result = {
            "primary_intent": intent,
            "intent_confidence": round(confidence, 3),
            "days_claimed": days_claimed,
            "signals": signals,
            "category": category,
        }

        logger.info(f"Stride analysis for '{user_text}': {result}")
        return result

    except Exception as e:
        logger.error(f"Analyzer failure: {e}", exc_info=True)
        return {
            "primary_intent": "inspection_request",
            "intent_confidence": 0.0,
            "days_claimed": None,
            "signals": {
                "manufacturing_defect": False,
                "misuse_or_wear": False,
                "intentional_damage": False,
            },
            "category": "inspection_request",
        }
