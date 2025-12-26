# Services/policy_chunker.py (upgraded: SRP helpers, compiled regex, safer parsing, better typing)

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from Services.logger_config import logger


# -----------------------------
# Regex (compiled once)
# -----------------------------
RE_BULLET = re.compile(r"^\s*[*-]\s+(.*)", re.MULTILINE)

RE_TITLE = re.compile(r"^###\s+(.*)$", re.MULTILINE)

RE_DECISION = re.compile(r"`decision`:\s*['\"]?(\w+)['\"]?", re.IGNORECASE)
RE_MAX_DAYS = re.compile(r"`max_days`:\s*(None|\d+)", re.IGNORECASE)
RE_MIN_DAYS = re.compile(r"`min_days`:\s*(\d+)", re.IGNORECASE)
RE_INTENTS = re.compile(r"`eligible_intents`:\s*(\[[^\]]*\])", re.IGNORECASE)

RE_SECTION_SPLIT = re.compile(r"\n(?=###\s+)")
RE_DOC_TITLE = re.compile(r"^##\s+.*?\n", re.MULTILINE)

RE_ELIGIBILITY = re.compile(
    r"\*\*(?:Eligibility|Trigger Conditions).*?\*\*[:\s]*(.*?)(?=\*\*Ineligible|\*\*Resolution|$)",
    re.S | re.I,
)
RE_INELIGIBLE = re.compile(
    r"\*\*Ineligible Conditions.*?\*\*[:\s]*(.*?)(?=\*\*Resolution|$)",
    re.S | re.I,
)
RE_RESOLUTION = re.compile(
    r"\*\*Resolution Outcome.*?\*\*[:\s]*(.*?)(?=\*\*Metadata|$)",
    re.S | re.I,
)


@dataclass(frozen=True)
class PolicyMetadata:
    decision: Optional[str]
    min_days: int
    max_days: Optional[int]
    eligible_intents: List[str]


@dataclass(frozen=True)
class PolicyChunk:
    policy_type: str
    metadata: Dict[str, Any]
    Content: Dict[str, List[str]]
    raw_content: str


# -----------------------------
# SRP helpers
# -----------------------------
def extract_list_items(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [m.strip() for m in RE_BULLET.findall(text) if m.strip()]


def extract_metadata(section_text: str) -> Dict[str, Any]:
    """
    Extracts automation-specific variables from the 'Metadata for Automation' section.
    Returns a dict compatible with your ingestion/retriever: min_days, max_days, eligible_intents, decision.
    """
    meta = PolicyMetadata(decision=None, min_days=0, max_days=None, eligible_intents=[])

    m = RE_DECISION.search(section_text)
    decision = m.group(1) if m else None

    m = RE_MAX_DAYS.search(section_text)
    max_days: Optional[int] = None
    if m:
        raw = m.group(1)
        max_days = int(raw) if raw.isdigit() else None

    m = RE_MIN_DAYS.search(section_text)
    min_days = int(m.group(1)) if m else 0

    intents: List[str] = []
    m = RE_INTENTS.search(section_text)
    if m:
        try:
            parsed = ast.literal_eval(m.group(1))
            intents = parsed if isinstance(parsed, list) else []
        except Exception:
            logger.warning("Could not parse eligible_intents list in metadata.", exc_info=True)
            intents = []

    return {
        "decision": decision,
        "min_days": min_days,
        "max_days": max_days,
        "eligible_intents": intents,
    }


def _extract_policy_type(section_text: str) -> str:
    m = RE_TITLE.search(section_text)
    return (m.group(1).strip() if m else "Unknown Policy")


def _extract_structured_content(section_text: str) -> Dict[str, List[str]]:
    eligibility = extract_list_items(RE_ELIGIBILITY.search(section_text).group(1)) if RE_ELIGIBILITY.search(section_text) else []
    ineligible = extract_list_items(RE_INELIGIBLE.search(section_text).group(1)) if RE_INELIGIBLE.search(section_text) else []
    resolution = extract_list_items(RE_RESOLUTION.search(section_text).group(1)) if RE_RESOLUTION.search(section_text) else []

    return {"Eligibility": eligibility, "Ineligible": ineligible, "Resolution": resolution}


def split_policies_into_chunks(md_path: str) -> List[Dict[str, Any]]:
    """
    Reads a Markdown file and returns a list of dicts:
      {policy_type, metadata, Content, raw_content}
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()

        # Remove main doc title (## ...)
        text = RE_DOC_TITLE.sub("", text)

        sections = RE_SECTION_SPLIT.split(text)

        chunks: List[Dict[str, Any]] = []
        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Keep the same filter behavior
            if "Metadata for Automation" not in section:
                continue

            policy_type = _extract_policy_type(section)
            metadata = extract_metadata(section)
            content = _extract_structured_content(section)

            chunks.append(
                {
                    "policy_type": policy_type,
                    "metadata": metadata,
                    "Content": content,
                    "raw_content": section,
                }
            )

        logger.info(f"Successfully split and structured {len(chunks)} policies from {md_path}.")
        return chunks

    except FileNotFoundError:
        logger.error(f"Policy file not found at path: {md_path}")
        return []
    except Exception as e:
        logger.error(f"Failed to process policies: {e}", exc_info=True)
        return []
