# semantic_analyzer.py (upgraded)
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Literal

import ollama
from pydantic import BaseModel, Field, ValidationError

from Services.logger_config import logger


Intent = Literal[
    "refund_request",
    "return_request",
    "replacement_request",
    "repair_request",
    "inspection_request",
    "general_chat",
]


class IntentModelOutput(BaseModel):
    intent: Intent = "general_chat"
    confidence: int = Field(0, ge=0, le=100)
    reason: str = ""
    misuse_or_accident: bool = False


class StrideIntentAnalyser:
    def __init__(
        self,
        model: str = "llama3.2:3b",
        temperature: float = 0.0,
        min_confidence: int = 50,
        client: Optional[ollama.Client] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.min_confidence = min_confidence
        self.client = client  # preferred: pass request.app.state.llm

        self.system_prompt = """
You are an intent classifier for a shoe support chatbot.

Return ONLY valid minified JSON (no markdown, no extra text), matching EXACTLY this schema:
{"intent":"refund_request|return_request|replacement_request|repair_request|inspection_request|general_chat",
 "confidence":0-100,
 "reason":"short",
 "misuse_or_accident":true|false}

Rules:
- If user greets + mentions a shoe problem but provides no specific request, set intent="inspection_request".
- If the user mentions accident/mishandling/pet damage/wear&tear, set misuse_or_accident=true and intent="inspection_request".
- If clearly asking for money back -> refund_request.
- If clearly wants to return because fit/style -> return_request.
- If clearly wants a new pair replacement -> replacement_request.
- If clearly wants repair for defect -> repair_request.
- If no shoe issue -> general_chat.

Example output:
{"intent":"inspection_request","confidence":65,"reason":"User mentions shoe issue but no specific request.","misuse_or_accident":false}
""".strip()

    def _generate_raw(self, user_text: str) -> Dict[str, Any]:
        try:
            # Prefer injected client if available (more consistent with main.py)
            if self.client is not None:
                resp = self.client.generate(
                    model=self.model,
                    system=self.system_prompt,
                    prompt=f"User text: {user_text}",
                    format="json",
                    options={"temperature": self.temperature},
                )
            else:
                resp = ollama.generate(
                    model=self.model,
                    system=self.system_prompt,
                    prompt=f"User text: {user_text}",
                    format="json",
                    options={"temperature": self.temperature},
                )

            return json.loads(resp.get("response", "{}"))
        except Exception as e:
            logger.error(f"Intent model call/parse failed: {e}", exc_info=True)
            return {}

    def analyse(self, user_text: str) -> Dict[str, Any]:
        raw = self._generate_raw(user_text)

        try:
            parsed = IntentModelOutput.model_validate(raw)
        except ValidationError as e:
            logger.warning(f"Invalid intent JSON from model: {e}")
            parsed = IntentModelOutput(
                intent="general_chat", confidence=0, reason="Invalid model output"
            )

        # Confidence guardrail: force safe path
        if parsed.confidence < self.min_confidence and parsed.intent != "general_chat":
            return {
                "primary_intent": "inspection_request",
                "intent": "inspection_request",
                "confidence": parsed.confidence,
                "misuse_or_accident": parsed.misuse_or_accident,
                "reason": f"Low confidence ({parsed.confidence}). Routed to inspection_request.",
            }

        # Grouping (keep your existing API contract)
        if parsed.intent in {"refund_request", "return_request"}:
            return {
                "primary_intent": parsed.intent,
                "intent": "return_refund_request",
                "confidence": parsed.confidence,
                "misuse_or_accident": parsed.misuse_or_accident,
                "reason": parsed.reason or "Return/refund intent detected",
            }

        if parsed.intent in {"repair_request", "replacement_request"}:
            return {
                "primary_intent": parsed.intent,
                "intent": "replacement_repair_request",
                "confidence": parsed.confidence,
                "misuse_or_accident": parsed.misuse_or_accident,
                "reason": parsed.reason or "Repair/replacement intent detected",
            }

        # Override: misuse beats user-requested category (your original rule)
        if (
            parsed.intent not in {"inspection_request", "general_chat"}
            and parsed.misuse_or_accident
        ):
            return {
                "primary_intent": "inspection_request",
                "intent": "inspection_request",
                "confidence": parsed.confidence,
                "misuse_or_accident": parsed.misuse_or_accident,
                "reason": f"Override: User requested {parsed.intent}, but misuse/accident was flagged.",
            }

        return {
            "primary_intent": parsed.intent,
            "intent": parsed.intent,
            "confidence": parsed.confidence,
            "misuse_or_accident": parsed.misuse_or_accident,
            "reason": parsed.reason or "Intent classified",
        }