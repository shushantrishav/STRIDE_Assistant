# ---------------------------------------------------
# Main.py
# ---------------------------------------------------
from fastapi import FastAPI
from Scripts.Model_Init import load_model
from Services.prompt_builder import StridePromptBuilder
from api.staff import router as staff_router
from api.chat import router as chat_router
from api.admin import router as admin_router
from Services.logger_config import logger

app = FastAPI(title="STRIDE Complaint Service")

@app.on_event("startup")
def startup_event():
    try:
        # Load heavy objects and store in app state
        app.state.llm = load_model()
        app.state.prompt_builder = StridePromptBuilder()
        logger.info("Startup complete: Model and PromptBuilder loaded successfully.")
    except Exception as e:
        logger.error(f"Error during startup: {e}", exc_info=True)
        raise e  # Let FastAPI handle the failure if startup fails

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
