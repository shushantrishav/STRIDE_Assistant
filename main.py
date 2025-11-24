# ---------------------------------------------------
# Main.py
# ---------------------------------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # Import Middleware
from Services.prompt_builder import StridePromptBuilder
from api.chat import router as chat_router
from api.admin import router as admin_router
from api.staff import router as staff_router
from Services.logger_config import logger
from cache.orders import prefetch_orders
import ollama

app = FastAPI(title="STRIDE Complaint Service")

# CORS Configuration
# ---------------------------------------------------
# Add the origins you want to allow. Use ["*"] to allow all (not recommended for production).
origins = [
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # List of allowed origins
    allow_credentials=True,           # Allow cookies/auth headers
    allow_methods=["*"],              # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],              # Allow all headers
)

@app.on_event("startup")
def startup_event():
    try:
        prefetch_orders(180)
        logger.info("Orders prefetched successfully")
        # Load heavy objects and store in app state
        app.state.llm = ollama.Client()
        app.state.prompt_builder = StridePromptBuilder()
        logger.info("Startup complete: Model and PromptBuilder loaded successfully.")
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise e 

# Include Routers
# ---------------------------------------------------
try:
    app.include_router(chat_router)
    app.include_router(staff_router)
    app.include_router(admin_router)
    logger.info("Routers registered successfully.")
except Exception as e:
    logger.error(f"Error including routers: {e}", exc_info=True)

@app.get("/")
def health_check():
    try:
        return {"status": "online", "service": "STRIDE Complaint API"}
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {"status": "error", "message": "Service health check failed."}