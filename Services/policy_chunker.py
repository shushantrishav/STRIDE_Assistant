# ==========================================
# STRIDE – POLICY CHUNKER
# ==========================================

import re
from Services.logger_config import logger  # import logger

def split_policies_into_chunks(md_path: str):
    """
    Splits policy markdown into semantic chunks
    based on headings (##).
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
        logger.info(f"Policy markdown loaded from '{md_path}'")

        # Split on headings
        sections = re.split(r"\n##\s+", text)
        chunks = []

        for section in sections:
            if not section.strip():
                continue

            lines = section.splitlines()
            title = lines[0].strip()
            content = "\n".join(lines[1:]).strip()

            chunks.append({
                "policy_type": title,
                "content": content
            })

        logger.info(f"Split policies into {len(chunks)} chunks")
        return chunks

    except FileNotFoundError:
        logger.error(f"Policy file not found: '{md_path}'", exc_info=True)
        return []

    except Exception as e:
        logger.error(f"Error splitting policy file '{md_path}': {e}", exc_info=True)
        return []
