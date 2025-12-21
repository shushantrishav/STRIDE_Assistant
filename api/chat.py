# ---------------------------------------------------
# api/chat.py
# ---------------------------------------------------
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError
from dotenv import load_dotenv
from Services.logger_config import logger

from db.sales import get_order_by_id
from db.tickets import get_ticket_by_order
from db.chat import (
    create_conversation,
    save_message,
    save_conversation_summary_with_ticket,
    get_conversation_for_review,
)
from Services.rag_pipeline import RAGPipeline

router = APIRouter(prefix="/chat", tags=["Chat"])

# --- ENV / JWT CONFIG ---
load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGO = "HS256"
SESSION_TTL_MINUTES = 30
FINAL_TOKEN_TTL_MINUTES = 5
ISSUER = "stride-customer-session"

security = HTTPBearer()


# --- SCHEMAS ---
class ChatStartRequest(BaseModel):
    order_id: str
    phone: str
    message: str


class ChatRespondRequest(BaseModel):
    message: str


# --- HELPERS ---
def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-10:]


def create_session_token(order_id: str, conversation_id: str, turn: int):
    now = datetime.utcnow()
    payload = {
        "sub": order_id,
        "conversation_id": conversation_id,
        "turn": turn,
        "finalized": False,
        "iat": now,
        "exp": now + timedelta(minutes=SESSION_TTL_MINUTES),
        "iss": ISSUER,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def create_finalized_token(order_id: str, conversation_id: str):
    now = datetime.utcnow()
    payload = {
        "sub": order_id,
        "conversation_id": conversation_id,
        "turn": "COMPLETED",
        "finalized": True,
        "iat": now,
        "exp": now + timedelta(minutes=FINAL_TOKEN_TTL_MINUTES),
        "iss": ISSUER,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def verify_session(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGO], issuer=ISSUER
        )
        if payload.get("finalized") is True:
            raise HTTPException(401, "Session already completed")
        return payload
    except JWTError as e:
        logger.warning(f"Invalid session token: {e}")
        raise HTTPException(401, "Invalid or expired session")


def map_order_row(row):
    if not row:
        return None

    columns = [
        "order_id",
        "product_id",
        "size",
        "customer_id",
        "outlet_id",
        "purchase_date",
        "price",
        "category",
        "customer_phone",
    ]

    # If row is a dict
    if isinstance(row, dict):
        return {k: row.get(k) for k in columns}

    # If row is a tuple or list
    if isinstance(row, (tuple, list)):
        return dict(zip(columns, row))

    # Otherwise, try attribute access
    return {k: getattr(row, k, None) for k in columns}


def run_llm(request: Request, prompt: str) -> str:
    llm = request.app.state.llm
    try:
        output = llm(prompt, max_tokens=256)
        if isinstance(output, dict) and "choices" in output:
            return output["choices"][0]["text"].strip()
        return str(output).strip()
    except Exception as e:
        logger.error(f"LLM error: {e}", exc_info=True)
        return "Sorry, there was an error generating a response."


# ---------------------------------------------------
# Chat Start Endpoint
# ---------------------------------------------------
@router.post("/start")
def start_chat(request: Request, payload: ChatStartRequest):
    try:
        order_row = get_order_by_id(payload.order_id)
        order = map_order_row(order_row)
        if not order or normalize_phone(payload.phone) != normalize_phone(
            order["customer_phone"]
        ):
            logger.info(
                f"Invalid order/phone attempt: {payload.order_id}, {payload.phone}"
            )
            raise HTTPException(401, "Invalid Order ID or Phone Mismatch")

        conversation_id = create_conversation(payload.order_id)
        save_message(conversation_id, "user", payload.message)

        pipeline = RAGPipeline(order)
        result = pipeline.process_turn(payload.message)

        prompt = request.app.state.prompt_builder.build_final_prompt(
            user_query=payload.message,
            decision={
                "decision": "NEEDS_CLARIFICATION",
                "action": "ASK_CLARIFICATION",
                "generate_ticket": False,
                "ticket_type": None,
                "reason": "",
            },
            turn_count=1,
        )

        ai_message = run_llm(request, prompt)
        save_message(conversation_id, "assistant", ai_message)
        token = create_session_token(order["order_id"], conversation_id, turn=2)
        logger.info(
            f"Chat started for order {order['order_id']}, conversation {conversation_id}"
        )

        return {
            "session_token": token,
            "message": ai_message,
            "turn": 1,
            "signals": result.get("signals"),
        }
    except Exception as e:
        logger.error(f"Error starting chat: {e}", exc_info=True)
        raise HTTPException(500, "Failed to start chat")


# ---------------------------------------------------
# Chat Respond Endpoint
# ---------------------------------------------------
@router.post("/respond")
def respond_chat(
    request: Request, payload: ChatRespondRequest, session=Depends(verify_session)
):
    try:
        if session["turn"] != 2:
            raise HTTPException(409, "Invalid conversation turn")

        conversation_id, order_id = session["conversation_id"], session["sub"]
        order = map_order_row(get_order_by_id(order_id))

        save_message(conversation_id, "user", payload.message)
        existing_ticket = get_ticket_by_order(order_id)

        if existing_ticket:
            prompt = request.app.state.prompt_builder.build_final_prompt(
                user_query=payload.message,
                decision={
                    "decision": "EXISTING_TICKET",
                    "action": "SHOW_EXISTING",
                    "generate_ticket": False,
                    "ticket_type": existing_ticket[3],
                    "reason": f"Ticket exists ({existing_ticket[0]})",
                },
                turn_count=2,
            )
            ai_message = run_llm(request, prompt)
            logger.info(f"Existing ticket response sent for order {order_id}")
            return {
                "decision": "EXISTING_TICKET",
                "message": ai_message,
                "session_finalized": True,
                "final_token": create_finalized_token(order_id, conversation_id),
            }

        # Normal RAG Path
        convo_data = get_conversation_for_review(conversation_id)
        pipeline = RAGPipeline(order)
        final_result = None
        for msg in convo_data["messages"]:
            if msg["role"] == "user":
                final_result = pipeline.process_turn(msg["content"])

        final_ticket = final_result["final_ticket"]
        reason = final_result.get("decision_reason")

        save_conversation_summary_with_ticket(
            conversation_id=conversation_id,
            decision=final_ticket,
            reason=reason,
            order_ctx={
                **order,
                "days_since_purchase": (
                    datetime.utcnow().date() - order["purchase_date"]
                ).days,
                "warranty_days": 180,
                "notes": reason,
                "decision": final_ticket,
            },
        )

        prompt = request.app.state.prompt_builder.build_final_prompt(
            user_query=payload.message,
            decision={
                "decision": final_ticket,
                "action": "TICKET_GENERATED",
                "generate_ticket": True,
                "ticket_type": final_ticket,
                "reason": reason,
            },
            turn_count=2,
        )

        ai_message = run_llm(request, prompt)
        save_message(conversation_id, "assistant", ai_message)
        logger.info(f"Final ticket {final_ticket} generated for order {order_id}")

        return {
            "decision": final_ticket,
            "message": ai_message,
            "session_finalized": True,
            "final_token": create_finalized_token(order_id, conversation_id),
        }

    except Exception as e:
        logger.error(f"Error responding to chat: {e}", exc_info=True)
        raise HTTPException(500, "Failed to process chat response")
