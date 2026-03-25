"""JWT authentication for comobot web panel."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from loguru import logger

from comobot.db.connection import Database

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
DEVICE_TOKEN_EXPIRE_HOURS = 1
REFRESH_TOKEN_EXPIRE_DAYS = 30


class AuthManager:
    """Manages admin authentication with JWT tokens."""

    def __init__(self, db: Database, secret_key: str | None = None):
        self.db = db
        self._secret = secret_key or os.environ.get("COMOBOT_JWT_SECRET", "")

    async def ensure_jwt_secret(self) -> None:
        """Generate JWT secret if not set."""
        if self._secret:
            return
        self._secret = os.urandom(32).hex()
        logger.info("Generated JWT secret for this session")

    async def is_setup_complete(self) -> bool:
        row = await self.db.fetchone("SELECT COUNT(*) as c FROM admin")
        return row["c"] > 0 if row else False

    async def create_admin(self, username: str, password: str) -> None:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        await self.db.execute(
            "INSERT INTO admin (username, password) VALUES (?, ?)",
            (username, hashed),
        )
        logger.info("Admin user '{}' created", username)

    async def authenticate(self, username: str, password: str) -> str | None:
        """Authenticate and return a JWT token, or None if invalid."""
        row = await self.db.fetchone("SELECT password FROM admin WHERE username = ?", (username,))
        if not row:
            return None
        if not bcrypt.checkpw(password.encode(), row["password"].encode()):
            return None

        expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
        payload = {"sub": username, "exp": expire}
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def verify_token(self, token: str) -> str | None:
        """Verify JWT token and return username, or None if invalid."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[ALGORITHM])
            return payload.get("sub")
        except JWTError:
            return None

    async def change_password(self, username: str, new_password: str) -> bool:
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        cursor = await self.db.execute(
            "UPDATE admin SET password = ?, updated_at = datetime('now') WHERE username = ?",
            (hashed, username),
        )
        return cursor.rowcount > 0

    # --- Device token methods for Comobot Remote ---

    def create_device_token(self, device_id: str, username: str = "remote") -> str:
        """Create a short-lived JWT for a paired mobile device (1 hour)."""
        expire = datetime.utcnow() + timedelta(hours=DEVICE_TOKEN_EXPIRE_HOURS)
        payload = {"sub": username, "device_id": device_id, "type": "device", "exp": expire}
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def create_refresh_token(self, device_id: str) -> str:
        """Create a long-lived refresh token for a mobile device (30 days)."""
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {"device_id": device_id, "type": "refresh", "exp": expire}
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def verify_device_token(self, token: str) -> dict | None:
        """Verify a device JWT and return payload {sub, device_id, type}, or None."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=[ALGORITHM])
            if payload.get("type") not in ("device", "refresh"):
                return None
            return {
                "sub": payload.get("sub"),
                "device_id": payload.get("device_id"),
                "type": payload.get("type"),
            }
        except JWTError:
            return None
