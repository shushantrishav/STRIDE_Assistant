# tests/test_policy_chunker.py
from __future__ import annotations

from pathlib import Path

from Services.policy_chunker import split_policies_into_chunks


def test_chunker_parses_one_policy(tmp_path: Path):
    md = """
## STRIDE Policies

### 1. Return Policy
**Eligibility**:
* Item is unused
* Within 7 days

**Ineligible Conditions**:
* Damaged due to misuse

**Resolution Outcome**:
* Manual inspection

**Metadata for Automation**
`decision`: "manual"
`min_days`: 0
`max_days`: 7
`eligible_intents`: ["return_request", "refund_request"]
"""
    p = tmp_path / "policies.md"
    p.write_text(md, encoding="utf-8")

    chunks = split_policies_into_chunks(str(p))
    assert len(chunks) == 1
    c = chunks[0]
    assert c["policy_type"] == "1. Return Policy"
    assert c["metadata"]["min_days"] == 0
    assert c["metadata"]["max_days"] == 7
    assert "return_request" in c["metadata"]["eligible_intents"]
    assert "Item is unused" in c["Content"]["Eligibility"]
