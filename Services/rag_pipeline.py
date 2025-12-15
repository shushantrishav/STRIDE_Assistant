import uuid
from collections import Counter
from typing import Dict, Any
from cache.inventory import is_inventory_available, prefetch_inventory
from cache.orders import get_order_from_cache
from rag.retriever import retrieve_policy
from rag.decision_engine import StrideDecisionEngine
from rag.semantic_analyzer import StrideIntentAnalyser
from Services.prompt_builder import StridePromptBuilder
from Services.logger_config import logger


class STRIDERAGPipeline:
    """
    STRIDE RAG PIPELINE (Cache + Policy-Grounded + Decision-Aware)

    Responsibilities:
    - Retrieve relevant policies
    - Enforce decision engine rules
    - Prefetch and validate inventory
    - Load order + customer data from Redis cache
    - Generate LLM-ready prompt
    - Resolve final ticket using arbitration
    """

    def __init__(self, order_id: str, brand_name="Stride"):
        self.order_id = order_id
        self.engine = StrideDecisionEngine()
        self.prompt_builder = StridePromptBuilder(brand_name)
        self.analyzer = StrideIntentAnalyser()
        self.turn_count = 0
        self.general_chat_count: int = 0
        self.signals: list[str] = []
        self.inventory_available: bool | None = None
        self.ticket_created = False
        self.order: dict = self._load_order()
        logger.info(f"STRIDERAGPipeline initialized for order {order_id}")

    # -------------------------------------------------
    # Load order + customer from Redis cache
    # -------------------------------------------------
    def _load_order(self) -> dict:
        order = get_order_from_cache(self.order_id)
        if order:
            logger.info(f"Order loaded from cache: {self.order_id}")
        else:
            logger.warning(f"Order {self.order_id} not found in cache")
            order = {}
        return order

    # -------------------------------------------------
    # Inventory prefetch and check
    # -------------------------------------------------
    def check_inventory(self) -> bool:
        """
        Check if replacement inventory is available for the order.
        """
        try:
            logger.debug(f"Checking inventory for order {self.order_id}")

            available = is_inventory_available(
                self.order["outlet_id"],
                self.order["product_id"],
                self.order["size"],
            )

            logger.info(
                f"Inventory check: {'available' if available else 'unavailable'} "
                f"(order_id={self.order_id})"
            )

            return available

        except Exception as e:
            logger.error(
                f"Error checking inventory for order {self.order_id}: {e}",
                exc_info=True,
            )
            return False

    # -------------------------------------------------
    # Authoritative signal arbitration
    # -------------------------------------------------
    def resolve_final_ticket(self) -> str:
        try:
            counts = Counter(self.signals)
            unique = set(self.signals)

            if unique == {"REJECT"}:
                return "REJECT"
            if counts.get("REJECT", 0) == 2 and len(self.signals) == 4:
                non_reject = [s for s in self.signals if s != "REJECT"]
                return Counter(non_reject).most_common(1)[0][0]
            if len(unique) == 1:
                return self.signals[0]
            if unique.issubset({"REPAIR", "INSPECTION"}):
                return "REPAIR" if counts["REPAIR"] >= 3 else "INSPECTION"
            if unique == {"RETURN", "REPLACEMENT"}:
                return "REPLACEMENT"
            if "PAID_REPAIR" in counts and counts["PAID_REPAIR"] == len(self.signals):
                return "PAID_REPAIR"

            return counts.most_common(1)[0][0]
        except Exception as e:
            logger.error(f"Error resolving final ticket: {e}", exc_info=True)
            return "INSPECTION"

    # -------------------------------------------------
    # Build prompt for LLM
    # -------------------------------------------------
    def build_llm_prompt(
        self,
        user_query: str,
        decision: Dict[str, Any],
        needs_clarification: bool = False,
    ) -> str:
        return self.prompt_builder.build_final_prompt(
            user_query=user_query,
            decision=decision,
            needs_clarification=needs_clarification,
            turn_count=self.turn_count,
        )

    # -------------------------------------------------
    # Process a conversation turn
    # -------------------------------------------------
    def process_turn(self, user_text: str) -> Dict[str, Any]:

        try:
            # Analyze user input
            analysis = self.analyzer.analyse(user_text)

            if analysis.get("intent") == "general_chat":
                self.general_chat_count += 1

                # If 2 consecutive general chats, close the chat
                if self.general_chat_count >= 2:
                    return {
                        "final_ticket": "GCD",
                        "ai_message": "I am an automated support system for STRIDE. If you do not have an order-related issue to report, I will have to terminate this chat session to keep the line open for other customers.",
                        "signals": self.signals,
                        "turn_count": self.turn_count,
                        "decision_reason": "Repeated general chat",
                        "chat_closed": True,
                    }

                # Otherwise, politely redirect
                else:
                    return {
                        "final_ticket": "GCD",
                        "ai_message": "I am the STRIDE Support Assistant, and I'm dedicated to helping you with order or product issues. Do you have a specific problem with a STRIDE purchase I can help you with?",
                        "signals": self.signals,
                        "turn_count": self.turn_count,
                        "decision_reason": "General chat detected",
                        "chat_closed": False,
                    }

            else:
                # Reset counter if user provides a real query
                self.general_chat_count = 0

            # Prefetch inventory (5-min TTL)
            prefetch_inventory(
                self.order.get("outlet_id"),
                self.order.get("product_id"),
                self.order.get("size"),
            )

            self.turn_count += 1

            # Retrieve policy chunks
            policy_chunks = retrieve_policy(
                user_query=user_text,
                predicted_intent=analysis.get("intent"),
                order_data=self.order,
            )
            retriever_signal = (
                policy_chunks["policy_type"].upper() if policy_chunks else "INSPECTION"
            )
            self.signals.append(retriever_signal)

            # Decision Engine
            self.inventory_available = self.check_inventory()
            engine_result = self.engine.make_decision(
                order_data=self.order,
                analysis=analysis,
                inventory_available=self.inventory_available,
                turn_count=self.turn_count,
            )
            engine_signal = engine_result.get("ticket_type", "INSPECTION").upper()
            self.signals.append(engine_signal)

            logger.info(
                f"Turn {self.turn_count}: Retriever={retriever_signal}, Engine={engine_signal}, Inventory={'yes' if self.inventory_available else 'no'}"
            )

            # Clarification stage (only first turn)
            if self.turn_count == 1:
                llm_prompt = self.build_llm_prompt(
                    user_query=user_text,
                    decision=engine_result,
                    needs_clarification=True,
                )
                return {
                    "final_ticket": "T1",
                    "needs_clarification": True,
                    "ai_message": llm_prompt,
                    "signals": self.signals,
                    "turn_count": self.turn_count,
                }

            # Final arbitration
            final_ticket = self.resolve_final_ticket()

            # Inventory safety override
            if final_ticket == "REPLACEMENT" and not self.inventory_available:
                final_ticket = "INSPECTION"

            # Generate LLM prompt (human-friendly explanation)
            llm_prompt = self.build_llm_prompt(
                user_query=user_text, decision=engine_result
            )

            return {
                "final_ticket": final_ticket,
                "ai_message": llm_prompt,
                "signals": self.signals,
                "turn_count": self.turn_count,
                "decision_reason": engine_result.get("reason"),
            }

        except Exception as e:
            logger.error(f"Error processing turn {self.turn_count}: {e}", exc_info=True)
            return {
                "final_ticket": "INSPECTION",
                "ai_message": "Fallback: manual inspection required.",
                "signals": self.signals,
                "turn_count": self.turn_count,
                "decision_reason": "Error occurred, fallback to manual inspection",
            }
