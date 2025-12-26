# rag_pipeline.py
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from cache.inventory import is_inventory_available, prefetch_inventory
from cache.orders import get_order_from_cache
from rag.retriever import retrieve_policy
from rag.decision_engine import StrideDecisionEngine
from rag.semantic_analyzer import StrideIntentAnalyser
from Services.prompt_builder import StridePromptBuilder
from Services.logger_config import logger


class TicketSignal(str, Enum):
    REJECT = "REJECT"
    INSPECTION = "INSPECTION"
    REPAIR = "REPAIR"
    RETURN = "RETURN"
    REPLACEMENT = "REPLACEMENT"
    PAID_REPAIR = "PAID_REPAIR"


class PipelineFinalTicket(str, Enum):
    # Clarification / conversation control
    CLARIFICATION = "T1"
    GENERAL_CHAT = "GCD"

    # Real outcomes
    REJECT = "REJECT"
    INSPECTION = "INSPECTION"
    REPAIR = "REPAIR"
    RETURN = "RETURN"
    REPLACEMENT = "REPLACEMENT"
    PAID_REPAIR = "PAID_REPAIR"


@dataclass(frozen=True)
class PipelineSignal:
    source: str  # "retriever" | "engine"
    value: TicketSignal
    turn: int
    confidence: Optional[float] = None  # e.g., retriever match_score


class STRIDERAGPipeline:
    """
    STRIDE RAG PIPELINE (Cache + Policy-Grounded + Decision-Aware)

    SRP-oriented responsibilities:
    - Load order context
    - Handle general chat routing
    - Prefetch/check inventory
    - Run retrieval (instinct)
    - Run decision engine (logic)
    - Arbitrate signals across turns
    - Build LLM prompt
    """

    def __init__(self, order_id: str, brand_name: str = "Stride") -> None:
        self.order_id = order_id
        self.brand_name = brand_name

        self.engine = StrideDecisionEngine()
        self.prompt_builder = StridePromptBuilder(brand_name)
        self.analyzer = StrideIntentAnalyser()

        self.turn_count = 0
        self.general_chat_count = 0

        self.order: Dict[str, Any] = self._load_order()
        self.inventory_available: Optional[bool] = None

        self.signals: List[PipelineSignal] = []

        logger.info(f"STRIDERAGPipeline initialized for order_id={order_id}")

    # -----------------------------
    # Public API
    # -----------------------------
    def process_turn(self, user_text: str) -> Dict[str, Any]:
        """
        Returns a dict compatible with your existing API layer:
        - final_ticket
        - ai_message
        - signals
        - turn_count
        - decision_reason
        - (optional) needs_clarification, chat_closed
        """
        try:
            analysis = self._analyse_user_text(user_text)

            general_chat_response = self._handle_general_chat_if_needed(analysis)
            if general_chat_response is not None:
                return general_chat_response

            if not self._has_minimum_order_context():
                return self._manual_fallback(
                    reason="Order not found or missing required fields (outlet_id/product_id/size)."
                )

            self.turn_count += 1

            # Inventory
            self._prefetch_inventory()
            self.inventory_available = self._check_inventory_safe()

            # Instinct (retriever)
            retriever_signal, retriever_score = self._run_retriever(user_text, analysis)
            self._record_signal(
                source="retriever",
                signal=retriever_signal,
                confidence=retriever_score,
            )

            # Logic (engine)
            engine_result = self._run_decision_engine(analysis)
            engine_signal = self._normalize_signal(engine_result.get("ticket_type"))
            self._record_signal(source="engine", signal=engine_signal, confidence=None)

            logger.info(
                "Turn %s: retriever=%s(score=%s), engine=%s, inventory=%s",
                self.turn_count,
                retriever_signal.value,
                retriever_score,
                engine_signal.value,
                "yes" if self.inventory_available else "no",
            )

            # Clarification stage: do NOT arbitrate yet
            if self.turn_count == 1:
                prompt = self._build_llm_prompt(
                    user_query=user_text,
                    decision=engine_result,
                    needs_clarification=True,
                )
                return {
                    "final_ticket": PipelineFinalTicket.CLARIFICATION.value,
                    "needs_clarification": True,
                    "ai_message": prompt,
                    "signals": self._signals_for_response(),
                    "turn_count": self.turn_count,
                }

            final_ticket = self._resolve_final_ticket()

            # Safety override: replacement requires inventory
            if final_ticket == TicketSignal.REPLACEMENT and not self.inventory_available:
                final_ticket = TicketSignal.INSPECTION

            prompt = self._build_llm_prompt(user_query=user_text, decision=engine_result)

            return {
                "final_ticket": final_ticket.value,
                "ai_message": prompt,
                "signals": self._signals_for_response(),
                "turn_count": self.turn_count,
                "decision_reason": engine_result.get("reason"),
            }

        except Exception as e:
            logger.error(f"Error processing turn {self.turn_count}: {e}", exc_info=True)
            return self._manual_fallback(reason="Error occurred, fallback to manual inspection.")

    # -----------------------------
    # Order / inventory helpers
    # -----------------------------
    def _load_order(self) -> Dict[str, Any]:
        order = get_order_from_cache(self.order_id)
        if order:
            logger.info(f"Order loaded from cache: order_id={self.order_id}")
            return order
        logger.warning(f"Order not found in cache: order_id={self.order_id}")
        return {}

    def _has_minimum_order_context(self) -> bool:
        required = ("outlet_id", "product_id", "size")
        return all(self.order.get(k) for k in required)

    def _prefetch_inventory(self) -> None:
        prefetch_inventory(
            self.order.get("outlet_id"),
            self.order.get("product_id"),
            self.order.get("size"),
        )

    def _check_inventory_safe(self) -> bool:
        try:
            return is_inventory_available(
                self.order.get("outlet_id"),
                self.order.get("product_id"),
                self.order.get("size"),
            )
        except Exception as e:
            logger.error(f"Inventory check failed for order_id={self.order_id}: {e}", exc_info=True)
            return False

    # -----------------------------
    # NLP / chat control
    # -----------------------------
    def _analyse_user_text(self, user_text: str) -> Dict[str, Any]:
        return self.analyzer.analyse(user_text)

    def _handle_general_chat_if_needed(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if analysis.get("intent") != "general_chat":
            self.general_chat_count = 0
            return None

        self.general_chat_count += 1

        if self.general_chat_count >= 2:
            return {
                "final_ticket": PipelineFinalTicket.GENERAL_CHAT.value,
                "ai_message": (
                    "I am an automated support system for STRIDE. If you do not have an order-related "
                    "issue to report, I will have to terminate this chat session to keep the line open "
                    "for other customers."
                ),
                "signals": self._signals_for_response(),
                "turn_count": self.turn_count,
                "decision_reason": "Repeated general chat",
                "chat_closed": True,
            }

        return {
            "final_ticket": PipelineFinalTicket.GENERAL_CHAT.value,
            "ai_message": (
                "I am the STRIDE Support Assistant, and I'm dedicated to helping you with order or "
                "product issues. Do you have a specific problem with a STRIDE purchase I can help you with?"
            ),
            "signals": self._signals_for_response(),
            "turn_count": self.turn_count,
            "decision_reason": "General chat detected",
            "chat_closed": False,
        }

    # -----------------------------
    # Retriever (instinct)
    # -----------------------------
    def _run_retriever(self, user_text: str, analysis: Dict[str, Any]) -> Tuple[TicketSignal, Optional[float]]:
        policy = retrieve_policy(
            user_query=user_text,
            predicted_intent=analysis.get("intent"),
            order_data=self.order,
        )
        if not policy:
            return TicketSignal.INSPECTION, None

        policy_type = str(policy.get("policy_type", "")).upper()
        match_score = policy.get("match_score")

        # Map policy types into canonical signals
        mapped = self._normalize_signal(policy_type)
        return mapped, float(match_score) if match_score is not None else None

    # -----------------------------
    # Decision engine (logic)
    # -----------------------------
    def _run_decision_engine(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        return self.engine.make_decision(
            order_data=self.order,
            analysis=analysis,
            inventory_available=bool(self.inventory_available),
            turn_count=self.turn_count,
        )

    # -----------------------------
    # Signals + arbitration
    # -----------------------------
    def _record_signal(self, source: str, signal: TicketSignal, confidence: Optional[float]) -> None:
        self.signals.append(
            PipelineSignal(source=source, value=signal, turn=self.turn_count, confidence=confidence)
        )

    def _signals_for_response(self) -> List[Dict[str, Any]]:
        return [
            {"source": s.source, "value": s.value.value, "turn": s.turn, "confidence": s.confidence}
            for s in self.signals
        ]

    def _resolve_final_ticket(self) -> TicketSignal:
        """
        Engine-weighted arbitration:
        - engine vote weight = 2
        - retriever vote weight = 1
        """
        try:
            weighted_votes: List[str] = []
            for s in self.signals:
                weight = 2 if s.source == "engine" else 1
                weighted_votes.extend([s.value.value] * weight)

            counts = Counter(weighted_votes)
            unique = set(weighted_votes)

            # Preserve your special-case logic, but on weighted votes
            if unique == {TicketSignal.REJECT.value}:
                return TicketSignal.REJECT

            if unique.issubset({TicketSignal.REPAIR.value, TicketSignal.INSPECTION.value}):
                return TicketSignal.REPAIR if counts[TicketSignal.REPAIR.value] >= 3 else TicketSignal.INSPECTION

            if unique == {TicketSignal.RETURN.value, TicketSignal.REPLACEMENT.value}:
                return TicketSignal.REPLACEMENT

            # Strong unanimity for paid repair
            if counts.get(TicketSignal.PAID_REPAIR.value, 0) == len(weighted_votes):
                return TicketSignal.PAID_REPAIR

            return TicketSignal(counts.most_common(1)[0][0])

        except Exception as e:
            logger.error(f"Error resolving final ticket: {e}", exc_info=True)
            return TicketSignal.INSPECTION

    def _normalize_signal(self, raw: Any) -> TicketSignal:
        """
        Converts engine/retriever strings into canonical TicketSignal values.
        Accepts variants like 'PaidRepair', 'PAID_REPAIR', 'Paid_Repair', etc.
        """
        if raw is None:
            return TicketSignal.INSPECTION

        text = str(raw).strip().upper().replace("-", "_").replace(" ", "_")
        text = text.replace("__", "_")

        # common aliases
        aliases = {
            "PAIDREPAIR": "PAID_REPAIR",
            "PAID_REPAIR": "PAID_REPAIR",
            "PAID__REPAIR": "PAID_REPAIR",
            "INSPECT": "INSPECTION",
        }
        text = aliases.get(text, text)

        # policy_type might be something like "RETURN POLICY"
        if "RETURN" in text and "REPLAC" not in text:
            return TicketSignal.RETURN
        if "REPLAC" in text:
            return TicketSignal.REPLACEMENT
        if "REPAIR" in text and "PAID" in text:
            return TicketSignal.PAID_REPAIR
        if "REPAIR" in text:
            return TicketSignal.REPAIR
        if "REJECT" in text:
            return TicketSignal.REJECT

        return TicketSignal.INSPECTION

    # -----------------------------
    # Prompting + fallback
    # -----------------------------
    def _build_llm_prompt(self, user_query: str, decision: Dict[str, Any], needs_clarification: bool = False) -> str:
        return self.prompt_builder.build_final_prompt(
            user_query=user_query,
            decision=decision,
            needs_clarification=needs_clarification,
            turn_count=self.turn_count,
        )

    def _manual_fallback(self, reason: str) -> Dict[str, Any]:
        return {
            "final_ticket": TicketSignal.INSPECTION.value,
            "ai_message": "Fallback: manual inspection required.",
            "signals": self._signals_for_response(),
            "turn_count": self.turn_count,
            "decision_reason": reason,
        }
