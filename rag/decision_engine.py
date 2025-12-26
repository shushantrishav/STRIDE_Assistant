# decision_engine.py (upgraded: cleaner SRP helpers, safer dates, consistent ticket_type, less duplication)

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, Optional

from Services.logger_config import logger


class Decision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MANUAL = "manual"


class TicketType(str, Enum):
    REJECT = "REJECT"
    INSPECTION = "INSPECTION"
    RETURN = "RETURN"
    REPAIR = "REPAIR"
    REPLACEMENT = "REPLACEMENT"
    PAID_REPAIR = "PAID_REPAIR"


class Action(str, Enum):
    POLICY_REJECTION = "policy_rejection"
    GATHER_INFO = "gather_info"
    REFUND_EVALUATION = "refund_evaluation"
    REPLACEMENT_AUTHORIZED = "replacement_authorized"
    STOCK_OUT_INSPECTION = "stock_out_inspection"
    REPAIR_AUTHORIZED = "repair_authorized"
    PAID_REPAIR_OFFER = "paid_repair_offer"
    ERROR = "error"


@dataclass(frozen=True)
class EngineConfig:
    return_window_days: int = 7
    warranty_days: int = 180
    turn_limit: int = 3


class StrideDecisionEngine:
    """
    Logic brain (strict policy).

    Inputs:
      - order_data: must include purchase_date (YYYY-MM-DD or date)
      - analysis: must include primary_intent + misuse_or_accident (bool)
      - inventory_available: used for replacement decisions
      - turn_count: used for escalation
    """

    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()

    # -----------------------------
    # Public API
    # -----------------------------
    def make_decision(
        self,
        order_data: Dict[str, Any],
        inventory_available: bool,
        turn_count: int,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            primary_intent = (analysis.get("primary_intent") or "general_chat").strip()
            misuse_flag = bool(analysis.get("misuse_or_accident", False))
            days_used = self._days_used(order_data)

            # If purchase date missing/invalid, fail safe to manual inspection
            if days_used is None:
                return self._result(
                    order_data=order_data,
                    decision=Decision.MANUAL,
                    action=Action.GATHER_INFO,
                    ticket_type=TicketType.INSPECTION,
                    reason="Missing/invalid purchase_date. Manual inspection required.",
                    generate_ticket=True,
                    rule_code="DATA_QUALITY_PURCHASE_DATE",
                )

            # Rule -1: general chat -> reject (policy irrelevant)
            if primary_intent == "general_chat":
                return self._result(
                    order_data=order_data,
                    decision=Decision.REJECT,
                    action=Action.POLICY_REJECTION,
                    ticket_type=TicketType.REJECT,
                    reason="The message does not follow any policy.",
                    generate_ticket=False,
                    rule_code="RULE_NEG1_GENERAL_CHAT",
                )

            # Rule 3: turn limit escalation (do this early to cap loops)
            if turn_count >= self.config.turn_limit:
                return self._result(
                    order_data=order_data,
                    decision=Decision.MANUAL,
                    action=Action.GATHER_INFO,
                    ticket_type=TicketType.INSPECTION,
                    reason="Turn limit reached. Moving to manual review.",
                    generate_ticket=True,
                    rule_code="RULE_3_TURN_LIMIT",
                )

            # Rule 0: misuse/wear&tear/accident -> paid repair or reject depending on warranty
            if misuse_flag:
                return self._handle_misuse(order_data, days_used)

            # Rule 1: refund/return window
            if primary_intent in {"refund_request", "return_request"}:
                return self._handle_return_refund(order_data, days_used, primary_intent)

            # Rule 2: repair/replacement window
            if primary_intent in {"repair_request", "replacement_request"}:
                return self._handle_repair_replacement(
                    order_data=order_data,
                    days_used=days_used,
                    inventory_available=inventory_available,
                )

            # Default: needs more info
            return self._result(
                order_data=order_data,
                decision=Decision.MANUAL,
                action=Action.GATHER_INFO,
                ticket_type=TicketType.INSPECTION,
                reason="Clarification required.",
                generate_ticket=False,
                rule_code="DEFAULT_CLARIFICATION",
            )

        except Exception as e:
            logger.error(
                f"Error making decision for order {order_data.get('order_id')}: {e}",
                exc_info=True,
            )
            return self._result(
                order_data=order_data,
                decision=Decision.MANUAL,
                action=Action.ERROR,
                ticket_type=TicketType.INSPECTION,
                reason="Internal error while making decision",
                generate_ticket=False,
                rule_code="ERROR",
            )

    # -----------------------------
    # Rule handlers (SRP)
    # -----------------------------
    def _handle_misuse(self, order_data: Dict[str, Any], days_used: int) -> Dict[str, Any]:
        if days_used <= self.config.warranty_days:
            return self._result(
                order_data=order_data,
                decision=Decision.APPROVE,
                action=Action.PAID_REPAIR_OFFER,
                ticket_type=TicketType.PAID_REPAIR,
                reason="Product shows signs of misuse or wear. Offering paid repair.",
                generate_ticket=True,
                paid_service_flag=True,
                rule_code="RULE_0_MISUSE_IN_WARRANTY",
            )

        return self._result(
            order_data=order_data,
            decision=Decision.REJECT,
            action=Action.POLICY_REJECTION,
            ticket_type=TicketType.REJECT,
            reason="Product issue falls under misuse/wear and the warranty is expired. Not eligible for free service.",
            generate_ticket=False,
            rule_code="RULE_0_MISUSE_OUT_OF_WARRANTY",
        )

    def _handle_return_refund(
        self, order_data: Dict[str, Any], days_used: int, primary_intent: str
    ) -> Dict[str, Any]:
        if days_used > self.config.return_window_days:
            return self._result(
                order_data=order_data,
                decision=Decision.REJECT,
                action=Action.POLICY_REJECTION,
                ticket_type=TicketType.REJECT,
                reason=(
                    f"Request for {primary_intent} after {days_used} days. "
                    f"Policy limit is {self.config.return_window_days} days."
                ),
                generate_ticket=False,
                rule_code="RULE_1_RETURN_REFUND_TOO_LATE",
            )

        return self._result(
            order_data=order_data,
            decision=Decision.MANUAL,
            action=Action.REFUND_EVALUATION,
            ticket_type=TicketType.RETURN,
            reason="Refund/Return requested within policy window. Mandatory inspection required.",
            generate_ticket=True,
            rule_code="RULE_1_RETURN_REFUND_WITHIN_WINDOW",
        )

    def _handle_repair_replacement(
        self,
        order_data: Dict[str, Any],
        days_used: int,
        inventory_available: bool,
    ) -> Dict[str, Any]:
        # 0..7 days: replacement preferred if stock exists
        if days_used <= self.config.return_window_days:
            if inventory_available:
                return self._result(
                    order_data=order_data,
                    decision=Decision.APPROVE,
                    action=Action.REPLACEMENT_AUTHORIZED,
                    ticket_type=TicketType.REPLACEMENT,
                    reason="Replacement within policy window approved. Stock confirmed.",
                    generate_ticket=True,
                    rule_code="RULE_2_EARLY_REPLACEMENT_IN_STOCK",
                )

            return self._result(
                order_data=order_data,
                decision=Decision.MANUAL,
                action=Action.STOCK_OUT_INSPECTION,
                ticket_type=TicketType.INSPECTION,
                reason="Replacement eligible but stock unavailable. Manual review required.",
                generate_ticket=True,
                rule_code="RULE_2_EARLY_REPLACEMENT_STOCK_OUT",
            )

        # 7..180 days: repair in warranty
        if days_used <= self.config.warranty_days:
            return self._result(
                order_data=order_data,
                decision=Decision.APPROVE,
                action=Action.REPAIR_AUTHORIZED,
                ticket_type=TicketType.REPAIR,
                reason=f"In-warranty repair approved (days_used={days_used}).",
                generate_ticket=True,
                rule_code="RULE_2_REPAIR_IN_WARRANTY",
            )

        # >180 days: paid repair
        return self._result(
            order_data=order_data,
            decision=Decision.APPROVE,
            action=Action.PAID_REPAIR_OFFER,
            ticket_type=TicketType.PAID_REPAIR,
            reason=f"Warranty expired (days_used={days_used}). Converting to paid repair service.",
            generate_ticket=True,
            paid_service_flag=True,
            rule_code="RULE_2_PAID_REPAIR_OUT_OF_WARRANTY",
        )

    # -----------------------------
    # Utilities
    # -----------------------------
    def _days_used(self, order_data: Dict[str, Any]) -> Optional[int]:
        purchase_date = order_data.get("purchase_date")
        if not purchase_date:
            return None

        if isinstance(purchase_date, str):
            try:
                purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()
            except Exception:
                return None

        if not hasattr(purchase_date, "year"):
            return None

        return (date.today() - purchase_date).days

    def _result(
        self,
        order_data: Dict[str, Any],
        decision: Decision,
        action: Action,
        ticket_type: TicketType,
        reason: str,
        generate_ticket: bool,
        rule_code: str,
        paid_service_flag: bool = False,
    ) -> Dict[str, Any]:
        result = {
            "decision": decision.value,
            "action": action.value,
            "ticket_type": ticket_type.value,  # canonical (matches pipeline normalization)
            "reason": reason,
            "generate_ticket": generate_ticket,
            "paid_service_flag": paid_service_flag,
            "rule_code": rule_code,
        }
        logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
        return result
