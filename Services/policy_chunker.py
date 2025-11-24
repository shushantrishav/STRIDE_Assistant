# Services/policy_chunker.py
# ==============================================================================
# STRIDE – POLICY CHUNKER
# Optimized for parsing Stride Complaint & Service Policies into structured JSON.
# ==============================================================================

import re
import ast
from Services.logger_config import logger

def extract_list_items(text: str):
    """
    Parses a Markdown block to extract bulleted list items.

    Args:
        text (str): The raw text block containing bullet points (e.g., Eligibility criteria).

    Returns:
        list: A list of cleaned strings representing each bullet point. 
              Returns an empty list if no items are found.
    """
    if not text:
        return []
    
    # Regex finds lines starting with '*' (ignoring leading whitespace)
    # Using re.MULTILINE to treat each newline as the start of a string
    items = re.findall(r"^\s*\*\s*(.*)", text, re.MULTILINE)
    return [item.strip() for item in items if item.strip()]

def extract_metadata(content: str):
    """
    Extracts automation-specific variables from the 'Metadata for Automation' section.

    Looks for:
    - decision: The decision type accept/reject/manual.
    - max_days: The upper bound of the policy validity (int or None).
    - min_days: The lower bound of the policy validity (int).
    - eligible_intents: A list of intent tags mapped to the policy.

    Args:
        content (str): The full text of a single policy chunk.

    Returns:
        dict: A dictionary containing min_days, max_days, and eligible_intents.
    """
    
    metadata = {"decision": None,"min_days": 0, "max_days": None, "eligible_intents": []}
    
    # policy_type
    decision_type_match = re.search(r"`decision`:\s*['\"]?(\w+)['\"]?", content)
    if decision_type_match:
        metadata["decision"] = decision_type_match.group(1)

    # Extract max_days (handles numeric values or 'None')
    max_days_match = re.search(r"`max_days`:\s*(None|\d+)", content)
    if max_days_match:
        val = max_days_match.group(1)
        metadata["max_days"] = int(val) if val.isdigit() else None

    # Extract min_days
    min_days_match = re.search(r"`min_days`:\s*(\d+)", content)
    if min_days_match:
        metadata["min_days"] = int(min_days_match.group(1))

    # Extract eligible_intents list using safe literal evaluation
    intents_match = re.search(r"`eligible_intents`:\s*(\[.*?\])", content)
    if intents_match:
        try:
            metadata["eligible_intents"] = ast.literal_eval(intents_match.group(1))
        except Exception:
            logger.warning("Could not parse intent list in metadata.")
            
    return metadata

def split_policies_into_chunks(md_path: str):
    """
    Reads a Markdown file, splits it into individual policy chunks based on '###' 
    headers, and parses each chunk into a structured data format.

    The structure includes:
    - policy_type: The heading of the policy.
    - metadata: Automation rules (days, intents).
    - Content: Sub-sections for Eligibility, Ineligible conditions, and Resolution.

    Args:
        md_path (str): Path to the .md policy document.

    Returns:
        list: A list of dictionaries, where each dictionary represents a structured policy.
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
        
        # Step 1: Remove the main document title (## Level) to avoid creating an empty first chunk
        text = re.sub(r"^##\s+.*?\n", "", text, flags=re.MULTILINE)
        
        # Step 2: Split text into sections starting with '###'
        # Positive lookahead preserves the '###' in the resulting strings for title extraction
        sections = re.split(r"\n(?=###\s+)", text)
        
        chunks = []
        for section in sections:
            section = section.strip()
            # Skip sections that don't contain automation metadata (like intro or footer text)
            if not section or "Metadata for Automation" not in section:
                continue

            # Step 3: Extract the Policy Title (e.g., "1. Return Policy")
            title_match = re.search(r"###\s+(.*)", section)
            policy_type = title_match.group(1).strip() if title_match else "Unknown Policy"

            # Step 4: Extract Sub-sections using lookaheads to prevent cross-section bleeding
            
            # criteria_block: Text under 'Eligibility' or 'Trigger Conditions'
            criteria_block = re.search(
                r"\*\*(?:Eligibility|Trigger Conditions).*?\*\*[:\s]*(.*?)(?=\*\*Ineligible|\*\*Resolution|$)", 
                section, re.S | re.I
            )
            
            # ineligible_block: Text under 'Ineligible Conditions'
            ineligible_block = re.search(
                r"\*\*Ineligible Conditions.*?\*\*[:\s]*(.*?)(?=\*\*Resolution|$)", 
                section, re.S | re.I
            )
            
            # outcome_block: Text under 'Resolution Outcome'
            outcome_block = re.search(
                r"\*\*Resolution Outcome.*?\*\*[:\s]*(.*?)(?=\*\*Metadata|$)", 
                section, re.S | re.I
            )

            # Step 5: Convert extracted blocks into cleaned Python lists
            structured_content = {
                "Eligibility": extract_list_items(criteria_block.group(1)) if criteria_block else [],
                "Ineligible": extract_list_items(ineligible_block.group(1)) if ineligible_block else [],
                "Resolution": extract_list_items(outcome_block.group(1)) if outcome_block else []
            }

            # Final Chunk Construction
            chunks.append({
                "policy_type": policy_type,
                "metadata": extract_metadata(section),
                "Content": structured_content,
                "raw_content": section  # Retained for context/RAG purposes
            })

        logger.info(f"Successfully split and structured {len(chunks)} policies from {md_path}.")
        return chunks

    except FileNotFoundError:
        logger.error(f"Policy file not found at path: {md_path}")
        return []
    except Exception as e:
        logger.error(f"Failed to process policies: {e}", exc_info=True)
        return []