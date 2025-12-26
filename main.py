# main.py (upgraded: lifespan + shutdown + safer CORS + clean structure)
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import ollama
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Services.logger_config import logger
from Services.prompt_builder import StridePromptBuilder
from cache.orders import prefetch_orders

from api.chat import router as chat_router
from api.admin import router as admin_router
from api.staff import router as staff_router


def _get_allowed_origins() -> list[str]:
    """
    Comma-separated list in CORS_ALLOW_ORIGINS.
    Example: "https://app.example.com,https://admin.example.com"
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # -------------------------
        # Startup
        # -------------------------
        logger.info("Starting STRIDE Complaint Service...")

        try:
            prefetch_orders(180)
            logger.info("Orders prefetched successfully.")
        except Exception as e:
            logger.error(f"Order prefetch failed: {e}", exc_info=True)
            # Fail-fast or continue based on preference.
            # For a mock, continuing might be acceptable:
            # raise

        try:
            app.state.llm = ollama.Client()
            app.state.prompt_builder = StridePromptBuilder()
            logger.info("Startup complete: Ollama client + PromptBuilder initialized.")
        except Exception as e:
            logger.error(f"Startup init failed: {e}", exc_info=True)
            raise

        # Yield control to the application
        yield

        # -------------------------
        # Shutdown
        # -------------------------
        logger.info("Shutting down STRIDE Complaint Service...")

        # If future versions of ollama client expose a close(), call it safely.
        llm: Optional[object] = getattr(app.state, "llm", None)
        close_fn = getattr(llm, "close", None)
        if callable(close_fn):
            try:
                close_fn()
                logger.info("LLM client closed successfully.")
            except Exception as e:
                logger.warning(f"Error while closing LLM client: {e}", exc_info=True)

        # Optional: cleanup state references
        for attr in ("llm", "prompt_builder"):
            if hasattr(app.state, attr):
                try:
                    delattr(app.state, attr)
                except Exception:
                    pass

        logger.info("Shutdown complete.")

    app = FastAPI(title="STRIDE Complaint Service", lifespan=lifespan)

    # -------------------------
    # CORS
    # -------------------------
    origins = _get_allowed_origins()

    # If origins == ["*"], allow_credentials should typically be False.
    # Keep your current behavior for mock compatibility, but safer default:
    allow_credentials = False if origins == ["*"] else True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------
    # Routers
    # -------------------------
    app.include_router(chat_router)
    app.include_router(staff_router)
    app.include_router(admin_router)

    @app.get("/")
    def health_check():
        return {"status": "online", "service": "STRIDE Complaint API"}

    return app


app = _build_app()
