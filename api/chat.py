import os
import re
import asyncio
from datetime import date, datetime, timedelta
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError
from dotenv import load_dotenv
from Services.logger_config import logger

from cache.orders import get_order_from_cache
from db.tickets import get_ticket_by_order
from db.chat import (
    create_conversation,
    save_message,
    save_conversation_summary_with_ticket,
    get_conversation_for_review,
)
from Services.rag_pipeline import STRIDERAGPipeline

router = APIRouter(prefix="/chat", tags=["Chat"])

# ---------------------------------------------------
# ENV / JWT CONFIG
# ---------------------------------------------------
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGO = "HS256"

CHAT_TOKEN_TTL_MINUTES = 30
CHAT_ISSUER = "stride-chat"

security = HTTPBearer()
MODEL_NAME = "llama3:8b"


# ---------------------------------------------------
# SCHEMAS
# ---------------------------------------------------
class ChatAuthRequest(BaseModel):
    order_id: str
    phone: str


class ChatMessageRequest(BaseModel):
    message: str


# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------
def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-10:]


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
        "full_name",
        "customer_phone",
    ]
    if isinstance(row, dict):
        return {k: row.get(k) for k in columns}
    if isinstance(row, (tuple, list)):
        return dict(zip(columns, row))
    return {k: getattr(row, k, None) for k in columns}


async def run_llm_generator(
    request: Request, user_query: str, sys_prompt: str
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields chunks from the synchronous Ollama client.
    Uses asyncio.to_thread to prevent blocking the event loop.
    """
    llm = request.app.state.llm
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_query},
    ]

    def get_ollama_stream():
        return llm.chat(model=MODEL_NAME, messages=messages, stream=True)

    try:
        stream = await asyncio.to_thread(get_ollama_stream)

        for chunk in stream:
            if isinstance(chunk, dict):
                content = chunk.get("message", {}).get("content", "")
            else:
                content = getattr(chunk, "message", {}).get("content", "")

            if content:
                yield content
                await asyncio.sleep(0)  # flush buffer

    except Exception as e:
        logger.error(f"Ollama LLM streaming error: {e}", exc_info=True)
        yield "[Error: Connection to AI model failed.]"


# ---------------------------------------------------
# JWT HELPERS
# ---------------------------------------------------
def create_chat_token(order_id: str, conversation_id: str) -> str:
    now = datetime.utcnow()
    return jwt.encode(
        {
            "sub": order_id,
            "conversation_id": conversation_id,
            "iat": now,
            "exp": now + timedelta(minutes=CHAT_TOKEN_TTL_MINUTES),
            "iss": CHAT_ISSUER,
        },
        JWT_SECRET,
        algorithm=JWT_ALGO,
    )


def verify_chat_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGO],
            issuer=CHAT_ISSUER,
        )
        return payload
    except JWTError:
        raise HTTPException(401, "Invalid or expired chat session")


# ---------------------------------------------------
# SSE STREAM HELPER
# ---------------------------------------------------
async def sse_stream(
    request: Request, user_query: str, sys_prompt: str, conversation_id: str
):
    """
    Streams the AI response as SSE 'data:' events.
    """
    full_ai_text = ""
    async for chunk in run_llm_generator(request, user_query, sys_prompt):
        for char in chunk:  # char-by-char typing effect
            full_ai_text += char
            yield f"data: {char}\n\n"
            await asyncio.sleep(0.005)  # optional typing delay

    # Save full assistant message after streaming
    if full_ai_text:
        save_message(conversation_id, "assistant", full_ai_text)

    # Signal end of stream
    yield "\ndata: [DONE]\n\n"


# ---------------------------------------------------
# /chat/auth
# ---------------------------------------------------
@router.post("/auth")
def chat_auth(request: Request, payload: ChatAuthRequest):
    order_row = get_order_from_cache(payload.order_id)
    order = map_order_row(order_row)

    if not order or normalize_phone(payload.phone) != normalize_phone(
        order["customer_phone"]
    ):
        logger.info(f"Chat auth failed for order {payload.order_id}")
        raise HTTPException(
            status_code=401,
            detail="Sorry, we could not verify your order details. Please check your Order ID and registered phone number and try again.",
        )

    conversation_id = create_conversation(payload.order_id)
    token = create_chat_token(payload.order_id, conversation_id)

    customer_name = order.get("full_name", "Customer")
    welcome_message = request.app.state.prompt_builder.build_welcome_prompt(
        customer_name=customer_name,
        order_id=payload.order_id,
    )

    return {
        "chat_token": token,
        "conversation_id": conversation_id,
        "message": welcome_message,  # ✅ plain text
    }


# ---------------------------------------------------
# /chat/start
# ---------------------------------------------------
@router.post("/start")
async def start_chat(
    request: Request,
    payload: ChatMessageRequest,
    session=Depends(verify_chat_token),
):
    order_id = session["sub"]
    conversation_id = session["conversation_id"]

    save_message(conversation_id, "user", payload.message)

    order = map_order_row(get_order_from_cache(order_id))
    c_name = order.get("full_name", "Customer")

    if get_ticket_by_order(order_id):
        system_prompt = request.app.state.prompt_builder.build_ticket_exists_prompt(
            customer_name=c_name, order_id=order_id
        )
        return StreamingResponse(
            sse_stream(request, payload.message, system_prompt, conversation_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    pipeline = STRIDERAGPipeline(order_id=order_id)
    result = pipeline.process_turn(payload.message)
    if result["final_ticket"] == "GCD":
        return{
            result["ai_message"]
        }
    print(result["signals"])

    return StreamingResponse(
        sse_stream(request, payload.message, result["ai_message"], conversation_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ---------------------------------------------------
# /chat/respond
# ---------------------------------------------------
@router.post("/respond")
async def respond_chat(
    request: Request,
    payload: ChatMessageRequest,
    session=Depends(verify_chat_token),
):
    order_id = session["sub"]
    conversation_id = session["conversation_id"]

    save_message(conversation_id, "user", payload.message)

    convo_data = get_conversation_for_review(conversation_id)
    pipeline = STRIDERAGPipeline(order_id=order_id)

    final_result = None
    for role, text, *_ in convo_data["messages"]:
        if role == "user":
            final_result = pipeline.process_turn(text)

    if not final_result:
        raise HTTPException(500, "Failed to resolve conversation context")

    if final_result["final_ticket"] == "GCD":
        return{
            final_result["ai_message"]
        }

    final_ticket = final_result.get("final_ticket")
    reason = final_result.get("decision_reason")
    order = map_order_row(get_order_from_cache(order_id))

    save_conversation_summary_with_ticket(
        conversation_id=conversation_id,
        decision=final_ticket,
        reason=reason,
        order_ctx={
            **order,
            "days_since_purchase": (
                date.today()
                - datetime.strptime(order["purchase_date"], "%Y-%m-%d").date()
            ).days,
            "warranty_days": 180,
            "notes": reason,
            "decision": final_ticket,
        },
    )

    return StreamingResponse(
        sse_stream(
            request, payload.message, final_result["ai_message"], conversation_id
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
