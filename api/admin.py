# ---------------------------------------------------
# api/admin.py
# ---------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt, JWTError
import os
from Services.logger_config import logger

from db.auth import authenticate_staff
from db.staff_audit import get_outlet_staff_logs

# ---------------------------------------------------
# Router setup
# ---------------------------------------------------
router = APIRouter(prefix="/admin", tags=["Admin"])

# ---------------------------------------------------
# JWT config
# ---------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = 60

security = HTTPBearer()

# ---------------------------------------------------
# Request schema
# ---------------------------------------------------
class AdminLoginRequest(BaseModel):
    username: str
    password: str

# ---------------------------------------------------
# Admin-only JWT dependency
# ---------------------------------------------------
def admin_only(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("role") != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        return payload  # staff_id, outlet_id, username, role
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

# ---------------------------------------------------
# ADMIN LOGIN (JWT ISSUED)
# ---------------------------------------------------
@router.post("/login")
def admin_login(payload: AdminLoginRequest):
    try:
        staff = authenticate_staff(payload.username, payload.password)

        if not staff:
            logger.info(f"Failed admin login attempt for username: {payload.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        staff_id, outlet_id, username, role = staff

        if role != "ADMIN":
            logger.warning(f"Non-admin staff tried to login as admin: {username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access only"
            )

        token_payload = {
            "sub": staff_id,
            "username": username,
            "outlet_id": outlet_id,
            "role": role,
            "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)
        }

        token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        logger.info(f"Admin logged in successfully: {username}")

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": JWT_EXP_MINUTES * 60
        }

    except Exception as e:
        logger.error(f"Admin login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )

# ---------------------------------------------------
# ADMIN VIEW OUTLET STAFF LOGS
# ---------------------------------------------------
@router.get("/logs")
def view_outlet_logs(
    limit: int = Query(100, ge=1, le=500),
    admin=Depends(admin_only)
):
    try:
        logs = get_outlet_staff_logs(
            outlet_id=admin["outlet_id"],
            limit=limit
        )
        logger.info(f"Admin {admin['username']} retrieved {len(logs)} logs.")
        return {
            "requested_by": {
                "staff_id": admin["sub"],
                "username": admin["username"],
                "outlet_id": admin["outlet_id"]
            },
            "count": len(logs),
            "logs": logs
        }
    except Exception as e:
        logger.error(f"Error retrieving outlet logs for admin {admin['username']}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch staff logs"
        )
