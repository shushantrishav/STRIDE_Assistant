# ==============================================================================
# STRIDE – EMBEDDER LAYER
# Single source of truth for text vectorization
# ==============================================================================

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Union
from Services.logger_config import logger

# Using a lightweight, high-performance model
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

try:
    # Load model once at the module level
    _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    logger.info(f"Embedder initialized: '{EMBED_MODEL_NAME}'")
except Exception as e:
    logger.error(f"Failed to load Embedder: {e}", exc_info=True)
    raise

def embed_text(text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    """
    Converts text into normalized vector embeddings.
    Returns: JSON serializable Python list(s).
    """
    try:
        # normalize_embeddings=True ensures cosine similarity is just a dot product
        embeddings = _embed_model.encode(text, normalize_embeddings=True)
        return embeddings.tolist()
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        return [] if isinstance(text, str) else [[] for _ in text]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates semantic closeness (0 to 1)."""
    try:
        a, b = np.array(v1), np.array(v2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    except Exception:
        return 0.0