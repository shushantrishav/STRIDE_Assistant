import uuid
from collections import Counter
from db.inventory import get_inventory_for_product
from db.tickets import create_ticket
from rag.retriever import retrieve_policy_chunks
from rag.decision_engine import StrideDecisionEngine
from rag.semantic_analyzer import analyze
from Services.logger_config import logger  # import logger

class RAGPipeline:
    """
    STRIDE RAG PIPELINE

    Retriever  -> observes intent (policy hint)
    Engine     -> enforces rules (authoritative)
    Pipeline   -> arbitrates + commits ticket
    """

    def __init__(self, order: dict):
        self.order = order
        self.engine = StrideDecisionEngine()
        self.turn_count = 0
        self.signals: list[str] = []  # Signals: [retriever_T1, engine_T1, retriever_T2, engine_T2]
        self.inventory_available: bool | None = None
        self.ticket_created = False
        logger.info(f"RAGPipeline initialized for order {order.get('order_id')}")

    # -------------------------------------------------
    # Inventory check
    # -------------------------------------------------
    def check_inventory(self) -> bool:
        try:
            row = get_inventory_for_product(
                self.order["outlet_id"],
                self.order["product_id"],
                self.order["size"],
            )
            available = row is not None and row[3] > 0
            logger.info(f"Inventory check: {'available' if available else 'unavailable'}")
            return available
        except Exception as e:
            logger.error(f"Error checking inventory: {e}", exc_info=True)
            return False

    # -------------------------------------------------
    # Signal resolution (AUTHORITATIVE LOGIC)
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
    # Conversation turn handler
    # -------------------------------------------------
    def process_turn(self, user_text: str) -> dict:
        self.turn_count += 1
        try:
            # RETRIEVER
            policy_chunks = retrieve_policy_chunks(user_text, self.order)
            retriever_signal = policy_chunks[0]["policy_type"].upper()
            self.signals.append(retriever_signal)

            # DECISION ENGINE
            self.inventory_available = self.check_inventory()
            analysis = analyze(user_text)

            engine_result = self.engine.make_decision(
                order_data=self.order,
                analysis=analysis,
                inventory_available=self.inventory_available,
                turn_count=self.turn_count,
            )

            raw_engine_ticket = engine_result.get("ticket_type")
            engine_signal = raw_engine_ticket.upper() if raw_engine_ticket else "INSPECTION"
            self.signals.append(engine_signal)

            logger.info(f"Turn {self.turn_count}: Retriever={retriever_signal}, Engine={engine_signal}, Inventory={'yes' if self.inventory_available else 'no'}")

            # CLARIFICATION (ONLY ONCE)
            if self.turn_count == 1:
                return {
                    "needs_clarification": True,
                    "ai_message": "Could you please explain the issue in a bit more detail?",
                    "signals": self.signals,
                    "turn_count": self.turn_count,
                }

            # FINAL ARBITRATION
            final_ticket = self.resolve_final_ticket()

            # Inventory safety override
            if final_ticket == "REPLACEMENT" and not self.inventory_available:
                final_ticket = "INSPECTION"

            return {
                "final_ticket": final_ticket,
                "signals": self.signals,
                "turn_count": self.turn_count,
                "decision_reason": engine_result.get("reason"),
            }

        except Exception as e:
            logger.error(f"Error processing turn {self.turn_count}: {e}", exc_info=True)
            return {
                "final_ticket": "INSPECTION",
                "signals": self.signals,
                "turn_count": self.turn_count,
                "decision_reason": "Error occurred, fallback to manual inspection",
            }
