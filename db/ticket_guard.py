# ticketsguard.py
# ==========================================
# STRIDE – TICKET VALIDATION & CREATION GUARD
# ==========================================
from cache.inventory import is_inventory_available
from db.tickets import has_active_ticket, create_ticket
from Services.logger_config import logger  # Import logger

# -------------------------------
# Validate & Optionally Create Ticket
# -------------------------------
def process_ticket(order_ticket_ctx: dict) -> dict:
    """
    Validate and create a ticket if allowed.

    order_ticket_ctx: dict
        {
            'order_id': str,
            'product_id': str,
            'outlet_id': str,
            'decision': str,         # 'REPAIR', 'REPLACEMENT', 'INSPECTION', etc
            'days_since_purchase': int,
            'warranty_days': int,
            'notes': str | None
        }

    Returns:
        {
            'allowed': bool,
            'reason': str | None,
            'ticket_id': str | None
        }
    """
    try:
        order_id = order_ticket_ctx["order_id"]
        decision = order_ticket_ctx["decision"]
        notes = order_ticket_ctx.get("notes")

        # 1️⃣ Check if an active ticket already exists
        if has_active_ticket(order_id):
            logger.warning(f"Ticket creation blocked: active ticket exists for order {order_id}")
            return {
                "allowed": False,
                "reason": "An active ticket already exists for this order",
                "ticket_id": None
            }

        # 2️⃣ Business rules
        ticket_type_to_create = decision
        final_notes = notes

        if decision == "REPLACEMENT":
            if not is_inventory_available(
                product_id=order_ticket_ctx["product_id"],
                outlet_id=order_ticket_ctx["outlet_id"],
                size=order_ticket_ctx["size"]
            ):
                # Inventory unavailable → fallback to INSPECTION
                ticket_type_to_create = "INSPECTION"
                final_notes = (
                    (notes + " | ") if notes else ""
                ) + "Replacement requested but inventory unavailable"
                logger.info(f"Replacement fallback to INSPECTION for order {order_id} due to inventory")

        if order_ticket_ctx["days_since_purchase"] > order_ticket_ctx["warranty_days"]:
            if decision not in {"REPAIR", "INSPECTION"}:
                logger.warning(f"Ticket creation blocked: warranty expired for order {order_id}")
                return {
                    "allowed": False,
                    "reason": "Warranty expired",
                    "ticket_id": None
                }

        # 3️⃣ Create ticket
        ticket_id = create_ticket(
            order_id=order_id,
            ticket_type=ticket_type_to_create,
            status="OPEN",
            outlet_id=order_ticket_ctx["outlet_id"],
            notes=final_notes
        )
        logger.info(f"Ticket created: order_id={order_id}, ticket_id={ticket_id}, type={ticket_type_to_create}")

        return {
            "allowed": True,
            "reason": None,
            "ticket_id": ticket_id
        }

    except Exception as e:
        logger.error(f"Error processing ticket for order {order_ticket_ctx.get('order_id')}: {e}", exc_info=True)
        return {
            "allowed": False,
            "reason": "Internal error while processing ticket",
            "ticket_id": None
        }
