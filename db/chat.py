# =====================================================
# db/chat.py
# =====================================================
import uuid
from db.postgres import get_connection
from db.ticket_guard import process_ticket
from Services.logger_config import logger  # Import logger

# ------------------------------------------
# Create Conversation
# ------------------------------------------
def create_conversation(order_id: str) -> str:
    conversation_id = str(uuid.uuid4())
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_schema.conversations
                    (conversation_id, order_id, started_at)
                    VALUES (%s, %s, now())
                """, (conversation_id, order_id))
        logger.info(f"Conversation created: {conversation_id} for order {order_id}")
        return conversation_id
    except Exception as e:
        logger.error(f"Error creating conversation for order {order_id}: {e}", exc_info=True)
        return None


# ------------------------------------------
# Save Message
# ------------------------------------------
def save_message(conversation_id: str, role: str, content: str):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_schema.messages
                    (message_id, conversation_id, role, content, created_at)
                    VALUES (%s, %s, %s, %s, now())
                """, (
                    str(uuid.uuid4()),
                    conversation_id,
                    role,
                    content
                ))
        logger.info(f"Message saved for conversation {conversation_id}, role {role}")
    except Exception as e:
        logger.error(f"Error saving message for conversation {conversation_id}: {e}", exc_info=True)


# ------------------------------------------
# Save Conversation Summary with Ticket Logic
# ------------------------------------------
def save_conversation_summary_with_ticket(conversation_id: str, decision: str, reason: str, order_ctx: dict):
    ticket_id = None
    try:
        if order_ctx:
            actionable_decisions = {"REPAIR", "REPLACEMENT", "PAID_REPAIR", "RETURN", "INSPECTION"}
            if decision in actionable_decisions:
                order_ctx["decision"] = decision
                order_ctx["notes"] = reason
                ticket_result = process_ticket(order_ctx)
                ticket_id = ticket_result.get("ticket_id")
                if ticket_result and not ticket_result["allowed"]:
                    reason = (reason or "") + f" | Ticket not created: {ticket_result['reason']}"

        DECISION_MAP = {
            "REPAIR": "APPROVE",
            "REPLACEMENT": "APPROVE",
            "PAID_REPAIR": "APPROVE",
            "RETURN": "APPROVE",
            "INSPECTION": "MANUAL",
            "REJECT": "REJECT",
            "APPROVE": "APPROVE",
            "MANUAL": "MANUAL"
        }
        schema_decision = DECISION_MAP.get(decision, "MANUAL")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_schema.conversation_summary
                    (conversation_id, decision, reason, ticket_id)
                    VALUES (%s, %s, %s, %s)
                """, (
                    conversation_id,
                    schema_decision,
                    reason,
                    ticket_id
                ))
        logger.info(f"Conversation summary saved for {conversation_id} with decision {schema_decision}")
    except Exception as e:
        logger.error(f"Error saving conversation summary for {conversation_id}: {e}", exc_info=True)


# ------------------------------------------
# Get Turn Count
# ------------------------------------------
def get_turn_count(conversation_id: str) -> int:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM chat_schema.messages 
                    WHERE conversation_id = %s
                """, (conversation_id,))
                row = cur.fetchone()
                count = row[0] if row else 0
                logger.info(f"Turn count for conversation {conversation_id}: {count}")
                return count
    except Exception as e:
        logger.error(f"Error fetching turn count for conversation {conversation_id}: {e}", exc_info=True)
        return 0


# ------------------------------------------
# Fetch Conversation for Manual Review
# ------------------------------------------
def get_conversation_for_review(conversation_id: str):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch conversation
                cur.execute("""
                    SELECT conversation_id, order_id, started_at
                    FROM chat_schema.conversations
                    WHERE conversation_id = %s
                """, (conversation_id,))
                convo = cur.fetchone()
                if not convo:
                    logger.warning(f"No conversation found with ID {conversation_id}")
                    return None

                # Fetch messages
                cur.execute("""
                    SELECT role, content, created_at
                    FROM chat_schema.messages
                    WHERE conversation_id = %s
                    ORDER BY created_at
                """, (conversation_id,))
                messages = cur.fetchall()

                # Fetch summary
                cur.execute("""
                    SELECT decision, reason, ticket_id
                    FROM chat_schema.conversation_summary
                    WHERE conversation_id = %s
                """, (conversation_id,))
                summary = cur.fetchone()

                logger.info(f"Fetched conversation {conversation_id} for review")
                return {
                    "conversation": convo,
                    "messages": messages,
                    "summary": summary
                }
    except Exception as e:
        logger.error(f"Error fetching conversation for review {conversation_id}: {e}", exc_info=True)
        return None
