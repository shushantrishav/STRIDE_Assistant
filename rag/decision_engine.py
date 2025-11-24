# ==========================================
# STRIDE – DECISION ENGINE (STRICT POLICY)
# ==========================================

from datetime import date, datetime
from typing import Dict, Any
from Services.logger_config import logger  # Import logger

class StrideDecisionEngine:
    """
    The 'Brain' of Stride. Enforces strict window-based approvals and rejections.
    """

    def __init__(self):
        pass

    def make_decision(
        self,
        order_data: Dict[str, Any],
        inventory_available: bool,
        turn_count: int,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculates outcome based on strict Stride policies.
        """
        try:
            # 1. Logic Variables
            purchase_date = order_data["purchase_date"]
            if isinstance(purchase_date, str):
                purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()

            days_used = (date.today() - purchase_date).days
            intent = analysis.get("intent")

            # ---------------------------------------------------------
            # RULE 0: MISUSE / WEAR & TEAR - Immediate Reject
            # ---------------------------------------------------------
            if intent == "misuse_or_wear":
                if days_used <= 180:
                    result = {
                        "decision": "approve",
                        "action": "paid_repair_offer",
                        "ticket_type": "Paid_Repair",
                        "reason": "Product shows signs of misuse or wear. Offering paid repair.",
                        "generate_ticket": True,
                        "paid_service_flag": True,
                    }
                else:
                    result = {
                        "decision": "reject",
                        "action": "policy_rejection",
                        "ticket_type": "Reject",
                        "reason": "Product shows signs of misuse or wear. Warranty expired. Not eligible for free repair.",
                        "generate_ticket": False,
                    }
                logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                return result

            # ---------------------------------------------------------
            # RULE 1: RETURNS / REFUNDS / REPLACEMENTS
            # ---------------------------------------------------------
            if intent in ["refund_request", "return_unused", "replacement_request"]:
                if days_used > 7:
                    result = {
                        "decision": "reject",
                        "action": "policy_rejection",
                        "ticket_type": "Reject",
                        "reason": f"Request for {intent} after {days_used} days. Policy limit is 7 days.",
                        "generate_ticket": False,
                    }
                    logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                    return result

                if intent == "replacement_request":
                    if inventory_available:
                        result = {
                            "decision": "approve",
                            "action": "replacement_authorized",
                            "ticket_type": "Replacement",
                            "reason": "Replacement within 7 days approved. Stock confirmed.",
                            "generate_ticket": True,
                        }
                    else:
                        result = {
                            "decision": "manual",
                            "action": "stock_out_inspection",
                            "ticket_type": "Inspection",
                            "reason": "Replacement eligible but stock unavailable. Manual review required.",
                            "generate_ticket": True,
                        }
                    logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                    return result

                if intent in ["refund_request", "return_unused"]:
                    result = {
                        "decision": "manual",
                        "action": "refund_evaluation",
                        "ticket_type": "Return",
                        "reason": "Refund/Return requested within 7 days. Mandatory inspection required.",
                        "generate_ticket": True,
                    }
                    logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                    return result

            # ---------------------------------------------------------
            # RULE 2: REPAIR FLOW (WARRANTY VS PAID)
            # ---------------------------------------------------------
            if intent in ["repair_request", "manufacturing_defect"]:
                if days_used <= 7:
                    if inventory_available:
                        result = {
                            "decision": "approve",
                            "action": "replacement_authorized",
                            "ticket_type": "Replacement",
                            "reason": "Replacement within 7 days approved. Stock confirmed.",
                            "generate_ticket": True,
                        }
                    else:
                        result = {
                            "decision": "manual",
                            "action": "stock_out_inspection",
                            "ticket_type": "Inspection",
                            "reason": "Replacement eligible but stock unavailable. Manual review required.",
                            "generate_ticket": True,
                        }
                    logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                    return result
                elif 7 < days_used <= 180:
                    result = {
                        "decision": "approve",
                        "action": "repair_authorized",
                        "ticket_type": "Repair",
                        "reason": f"In-warranty repair approved ({days_used} days).",
                        "generate_ticket": True,
                    }
                    logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                    return result
                else:
                    result = {
                        "decision": "approve",
                        "action": "paid_repair_offer",
                        "ticket_type": "Paid_Repair",
                        "reason": f"Warranty expired ({days_used} days). Converting to Paid_Repair service.",
                        "generate_ticket": True,
                        "paid_service_flag": True,
                    }
                    logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                    return result

            # ---------------------------------------------------------
            # RULE 3: TURN LIMIT CATCH-ALL
            # ---------------------------------------------------------
            if turn_count >= 3:
                result = {
                    "decision": "manual",
                    "action": "gather_info",
                    "ticket_type": "Inspection",
                    "reason": "Turn limit reached. Moving to manual review.",
                    "generate_ticket": True,
                }
                logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
                return result

            # DEFAULT: Needs more info
            result = {
                "decision": "manual",
                "action": "gather_info",
                "ticket_type": "Inspection",
                "reason": "Clarification required.",
                "generate_ticket": False,
            }
            logger.info(f"Decision made for order {order_data.get('order_id')}: {result}")
            return result

        except Exception as e:
            logger.error(f"Error making decision for order {order_data.get('order_id')}: {e}", exc_info=True)
            return {
                "decision": "manual",
                "action": "error",
                "ticket_type": "Inspection",
                "reason": "Internal error while making decision",
                "generate_ticket": False,
            }
