"""FastAPI dependency injection for comobot."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from comobot.db.connection import Database
from comobot.security.auth import AuthManager
from comobot.security.crypto import CredentialVault

security = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_auth(request: Request) -> AuthManager:
    return request.app.state.auth


def get_vault(request: Request) -> CredentialVault:
    return request.app.state.vault


def get_channels(request: Request):
    """Get ChannelManager from app state."""
    from comobot.channels.manager import ChannelManager

    cm: ChannelManager | None = getattr(request.app.state, "channels", None)
    if cm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Channel manager not available",
        )
    return cm


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Verify JWT and return username. Raises 401 if invalid."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    auth: AuthManager = request.app.state.auth
    username = auth.verify_token(credentials.credentials)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return username
