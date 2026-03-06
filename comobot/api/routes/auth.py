"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from comobot.api.deps import get_auth, get_current_user
from comobot.security.auth import AuthManager

router = APIRouter(prefix="/api/auth")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, auth: AuthManager = Depends(get_auth)):
    token = await auth.authenticate(body.username, body.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenResponse(access_token=token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    auth: AuthManager = Depends(get_auth),
    username: str = Depends(get_current_user),
):
    # Issue a fresh token for the already-authenticated user
    from datetime import datetime, timedelta

    from jose import jwt

    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {"sub": username, "exp": expire}
    new_token = jwt.encode(payload, auth._secret, algorithm="HS256")
    return TokenResponse(access_token=new_token)
