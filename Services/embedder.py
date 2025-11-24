# ==========================================
# STRIDE – EMBEDDER
# Single source of truth for embeddings
# ==========================================

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Union
from Services.logger_config import logger  # import logger

# ------------------------------------------
# Load embedding model ONCE
# ------------------------------------------
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

try:
    _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    logger.info(f"Embedder model '{EMBED_MODEL_NAME}' loaded successfully")
except Exception as e:
    logger.error(f"Error loading embedder model '{EMBED_MODEL_NAME}': {e}", exc_info=True)
    raise

# ------------------------------------------
# Public API
# ------------------------------------------
def embed_text(
    text: Union[str, List[str]]
) -> Union[List[float], List[List[float]]]:
    """
    Generate embeddings for text or list of texts.
    Returns Python lists (JSON serializable).
    """
    try:
        embeddings = _embed_model.encode(
            text,
            normalize_embeddings=True
        )

        if isinstance(text, list):
            logger.info(f"Generated embeddings for list of {len(text)} texts")
            return embeddings.tolist()

        logger.info("Generated embeddings for single text")
        return embeddings.tolist()

    except Exception as e:
        logger.error(f"Error generating embeddings for text '{text}': {e}", exc_info=True)
        if isinstance(text, list):
            return [[] for _ in text]
        return []

# ------------------------------------------
# Utility
# ------------------------------------------
def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    try:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    except Exception as e:
        logger.warning(f"Cosine similarity calculation failed: {e}", exc_info=True)
        return 0.0
