# chat.py (upgraded)
from __future__ import annotations

import os
import re
import asyncio
from datetime import date, datetime, timedelta
from typing import AsyncGenerator, Any, Dict, Optional, Tuple

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from Services.logger_config import logger
from Services.rag_pipeline import STRIDERAGPipeline

from cache.orders import get_order_from_cache
from db.chat import (
    create_conversation,
    get_conversation_for_review,
    save_conversation_summary_with_ticket,
    save_message,
)
from db.tickets import get_ticket_by_order


router = APIRouter(prefix="/chat", tags=["Chat"])

# -----------------------------
# ENV / JWT CONFIG
# -----------------------------
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGO = "HS256"

CHAT_TOKEN_TTL_MINUTES = 30
CHAT_ISSUER = "stride-chat"

security = HTTPBearer()

MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "llama3:8b")


# -----------------------------
# Schemas
# -----------------------------
class ChatAuthRequest(BaseModel):
    order_id: str = Field(..., min_length=3)
    phone: str = Field(..., min_length=8)


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


# -----------------------------
# Helpers
# -----------------------------
def _require_jwt_secret() -> None:
    if not JWT_SECRET:
        logger.error("JWT_SECRET_KEY is not set.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: JWT secret not set.",
        )


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-10:]


def map_order_row(row: Any) -> Optional[Dict[str, Any]]:
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
        "full_name",
        "customer_phone",
    ]

    if isinstance(row, dict):
        return {k: row.get(k) for k in columns}

    if isinstance(row, (tuple, list)):
        return dict(zip(columns, row))

    return {k: getattr(row, k, None) for k in columns}


def compute_days_since_purchase(order: Dict[str, Any]) -> Optional[int]:
    purchase_date = order.get("purchase_date")
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


# -----------------------------
# JWT helpers
# -----------------------------
def create_chat_token(order_id: str, conversation_id: str) -> str:
    _require_jwt_secret()
    now = datetime.utcnow()
    payload = {
        "sub": order_id,
        "conversation_id": conversation_id,
        "iat": now,
        "exp": now + timedelta(minutes=CHAT_TOKEN_TTL_MINUTES),
        "iss": CHAT_ISSUER,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def verify_chat_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    _require_jwt_secret()
    try:
        return jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGO],
            issuer=CHAT_ISSUER,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired chat session",
        )


# -----------------------------
# Ollama streaming
# -----------------------------
async def run_llm_generator(
    request: Request,
    user_query: str,
    system_prompt: str,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields chunks from a synchronous Ollama client using asyncio.to_thread.
    """
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        yield "[Error: LLM client not initialized]"
        return

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_query},
    ]

    def _ollama_stream():
        return llm.chat(model=MODEL_NAME, messages=messages, stream=True)

    try:
        stream = await asyncio.to_thread(_ollama_stream)

        for chunk in stream:
            if isinstance(chunk, dict):
                content = (chunk.get("message") or {}).get("content") or ""
            else:
                message = getattr(chunk, "message", None) or {}
                content = message.get("content") if isinstance(message, dict) else ""
            if content:
                yield content
                await asyncio.sleep(0)

    except Exception as e:
        logger.error(f"Ollama LLM streaming error: {e}", exc_info=True)
        yield "[Error: Connection to AI model failed.]"


async def sse_stream(
    request: Request,
    user_query: str,
    system_prompt: str,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """
    Streams the AI response as SSE 'data:' events.
    Saves the final assistant message after streaming completes.
    """
    full_text = ""
    async for chunk in run_llm_generator(request, user_query, system_prompt):
        # Prefer chunk-based streaming (lower CPU than char-by-char)
        full_text += chunk
        yield f"data: {chunk}\n\n"

    if full_text:
        save_message(conversation_id, "assistant", full_text)

    yield "data: [DONE]\n\n"


def _sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -----------------------------
# Internal chat flow helpers (SRP)
# -----------------------------
def _get_order_or_401(order_id: str, phone: str) -> Dict[str, Any]:
    order = map_order_row(get_order_from_cache(order_id))
    if not order:
        logger.info(f"Chat auth failed: order not found order_id={order_id}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Order not found.")

    if normalize_phone(phone) != normalize_phone(order.get("customer_phone") or ""):
        logger.info(f"Chat auth failed: phone mismatch order_id={order_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sorry, we could not verify your order details. Please check your Order ID and registered phone number and try again.",
        )

    return order


def _handle_gcd_if_needed(result: Dict[str, Any]) -> Optional[JSONResponse]:
    if result.get("final_ticket") != "GCD":
        return None
    # Always return JSON for GCD (don’t start SSE stream for a terminated/redirect flow)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "final_ticket": "GCD",
            "ai_message": result.get("ai_message"),
            "chat_closed": bool(result.get("chat_closed")),
            "turn_count": result.get("turn_count"),
            "decision_reason": result.get("decision_reason"),
        },
    )


# -----------------------------
# /chat/auth
# -----------------------------
@router.post("/auth")
def chat_auth(request: Request, payload: ChatAuthRequest):
    order = _get_order_or_401(payload.order_id, payload.phone)

    conversation_id = create_conversation(payload.order_id)
    token = create_chat_token(payload.order_id, conversation_id)

    customer_name = order.get("full_name") or "Customer"
    welcome_message = request.app.state.prompt_builder.build_welcome_prompt(
        customer_name=customer_name,
        order_id=payload.order_id,
    )

    return {
        "chat_token": token,
        "conversation_id": conversation_id,
        "message": welcome_message,
    }


# -----------------------------
# /chat/start
# -----------------------------
@router.post("/start")
async def start_chat(
    request: Request,
    payload: ChatMessageRequest,
    session: Dict[str, Any] = Depends(verify_chat_token),
):
    order_id = session["sub"]
    conversation_id = session["conversation_id"]

    save_message(conversation_id, "user", payload.message)

    order = map_order_row(get_order_from_cache(order_id)) or {}
    customer_name = order.get("full_name") or "Customer"

    # If a ticket already exists, skip pipeline and just inform user (streamed)
    if get_ticket_by_order(order_id):
        system_prompt = request.app.state.prompt_builder.build_ticket_exists_prompt(
            customer_name=customer_name,
            order_id=order_id,
        )
        return _sse_response(sse_stream(request, payload.message, system_prompt, conversation_id))

    pipeline = STRIDERAGPipeline(order_id=order_id)
    result = pipeline.process_turn(payload.message)

    gcd_response = _handle_gcd_if_needed(result)
    if gcd_response is not None:
        return gcd_response

    # Stream the LLM using the pipeline's built prompt
    return _sse_response(sse_stream(request, payload.message, result["ai_message"], conversation_id))


# -----------------------------
# /chat/respond
# -----------------------------
@router.post("/respond")
async def respond_chat(
    request: Request,
    payload: ChatMessageRequest,
    session: Dict[str, Any] = Depends(verify_chat_token),
):
    order_id = session["sub"]
    conversation_id = session["conversation_id"]

    save_message(conversation_id, "user", payload.message)

    convo_data = get_conversation_for_review(conversation_id)
    if not convo_data or "messages" not in convo_data:
        raise HTTPException(status_code=500, detail="Conversation not found or invalid.")

    pipeline = STRIDERAGPipeline(order_id=order_id)

    final_result: Optional[Dict[str, Any]] = None
    for role, text, *_ in convo_data["messages"]:
        if role == "user":
            final_result = pipeline.process_turn(text)

    if not final_result:
        raise HTTPException(status_code=500, detail="Failed to resolve conversation context")

    gcd_response = _handle_gcd_if_needed(final_result)
    if gcd_response is not None:
        return gcd_response

    final_ticket = final_result.get("final_ticket")
    reason = final_result.get("decision_reason")

    order = map_order_row(get_order_from_cache(order_id)) or {}
    days_since_purchase = compute_days_since_purchase(order)

    save_conversation_summary_with_ticket(
        conversation_id=conversation_id,
        decision=final_ticket,
        reason=reason,
        order_ctx={
            **order,
            "days_since_purchase": days_since_purchase,
            "warranty_days": 180,
            "notes": reason,
            "decision": final_ticket,
        },
    )

    return _sse_response(sse_stream(request, payload.message, final_result["ai_message"], conversation_id))
