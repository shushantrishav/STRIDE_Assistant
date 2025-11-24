# ---------------------------------------------------
# api/staff.py
# ---------------------------------------------------
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError
from dotenv import load_dotenv
from Services.logger_config import logger

from db.auth import authenticate_staff
from db.tickets import get_tickets_by_outlet, update_ticket_status
from db.staff_audit import log_staff_action

# =====================================================
# JWT CONFIG
# =====================================================
load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    logger.error(f"Error updating ticket: JWT_SECRET_KEY not set in environment variables", exc_info=True)    
    raise RuntimeError("JWT_SECRET_KEY not set in environment variables")

router = APIRouter(prefix="/staff", tags=["Staff"])
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8
ISSUER = "stride-staff-service"

security = HTTPBearer()

# =====================================================
# HELPERS
# =====================================================
def create_access_token(data: dict):
    """
    Create JWT token with immutable staff_id and outlet_id.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": ISSUER
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_staff(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Decode JWT and return staff identity.
    Ensures staff_id and outlet_id are immutable for session.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], issuer=ISSUER)
        required_claims = {"sub", "outlet_id", "role"}
        if not required_claims.issubset(payload):
            logger.warning(f"JWT missing required claims: {payload}")
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return {
            "staff_id": payload["sub"],
            "outlet_id": payload["outlet_id"],
            "role": payload["role"]
        }
    except JWTError as e:
        logger.warning(f"Invalid or expired token: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# =====================================================
# REQUEST MODELS
# =====================================================
class StaffLoginRequest(BaseModel):
    username: str
    password: str


class TicketUpdateRequest(BaseModel):
    ticket_id: str
    new_status: str
    notes: str | None = None


# =====================================================
# STAFF LOGIN
# =====================================================
@router.post("/login")
def staff_login(payload: StaffLoginRequest):
    try:
        staff = authenticate_staff(payload.username, payload.password)
        if not staff:
            logger.info(f"Failed login attempt for username: {payload.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        staff_id, outlet_id, username, role = staff
        token = create_access_token({"sub": staff_id, "outlet_id": outlet_id, "role": role})

        log_staff_action(staff_id=staff_id, action="STAFF_LOGGED_IN", target_id=None)
        logger.info(f"Staff {username} logged in successfully")
        return {"access_token": token, "token_type": "bearer", "expires_in_hours": ACCESS_TOKEN_EXPIRE_HOURS}
    except Exception as e:
        logger.error(f"Error in staff login: {e}", exc_info=True)
        raise HTTPException(500, "Staff login failed")


# =====================================================
# VIEW TICKETS
# =====================================================
@router.get("/tickets")
def view_tickets(staff=Depends(get_current_staff)):
    try:
        tickets = get_tickets_by_outlet(staff["outlet_id"])
        log_staff_action(staff_id=staff["staff_id"], action="VIEW_TICKETS", target_id=None)
        logger.info(f"Staff {staff['staff_id']} viewed {len(tickets)} tickets")
        return {"tickets": tickets}
    except Exception as e:
        logger.error(f"Error fetching tickets: {e}", exc_info=True)
        raise HTTPException(500, "Failed to retrieve tickets")


# =====================================================
# UPDATE TICKET STATUS
# =====================================================
@router.post("/tickets/update")
def update_ticket(payload: TicketUpdateRequest, staff=Depends(get_current_staff)):
    try:
        allowed_statuses = {"OPEN", "MANUAL_REVIEW", "RESOLVED", "CLOSED"}
        if payload.new_status not in allowed_statuses:
            logger.warning(f"Staff {staff['staff_id']} tried invalid status update: {payload.new_status}")
            raise HTTPException(status_code=400, detail="Invalid ticket status")

        update_ticket_status(
            ticket_id=payload.ticket_id,
            new_status=payload.new_status,
            staff_id=staff["staff_id"],
            notes=payload.notes
        )

        log_staff_action(
            staff_id=staff["staff_id"],
            action=f"TICKET_STATUS_UPDATED_TO_{payload.new_status}",
            target_id=payload.ticket_id
        )
        logger.info(f"Staff {staff['staff_id']} updated ticket {payload.ticket_id} to {payload.new_status}")
        return {"message": "Ticket updated successfully"}
    except Exception as e:
        logger.error(f"Error updating ticket: {e}", exc_info=True)
        raise HTTPException(500, "Failed to update ticket")
