from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest):
    if not settings.dashboard_password:
        raise HTTPException(500, "Dashboard password not configured. Run setup.sh first.")

    if body.username != settings.dashboard_username:
        raise HTTPException(401, "Invalid credentials")

    stored_hash = settings.dashboard_password.encode("utf-8")
    if not bcrypt.checkpw(body.password.encode("utf-8"), stored_hash):
        raise HTTPException(401, "Invalid credentials")

    token = jwt.encode(
        {
            "sub": body.username,
            "exp": datetime.utcnow() + timedelta(days=7),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"token": token}


@router.get("/me")
async def me(request: Request):
    return {"username": request.state.user}
