"""AES-256-GCM credential encryption for comobot."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from comobot.db.connection import Database


class CredentialVault:
    """Encrypts and stores credentials using AES-256-GCM."""

    def __init__(self, db: Database, secret_key: bytes | None = None):
        self.db = db
        self._key = secret_key or self._load_key()
        self._gcm = AESGCM(self._key)

    @staticmethod
    def _load_key() -> bytes:
        env_key = os.environ.get("COMOBOT_SECRET_KEY")
        if env_key:
            raw = env_key.encode() if isinstance(env_key, str) else env_key
            if len(raw) == 32:
                return raw
            from hashlib import sha256

            return sha256(raw).digest()

        key_path = Path.home() / ".comobot" / "secret.key"
        if key_path.exists():
            return key_path.read_bytes()[:32]

        key = os.urandom(32)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        logger.info("Generated new secret key at {}", key_path)
        return key

    def encrypt(self, plaintext: str) -> tuple[bytes, bytes, bytes]:
        """Encrypt plaintext. Returns (ciphertext, nonce, tag)."""
        nonce = os.urandom(12)
        ct = self._gcm.encrypt(nonce, plaintext.encode(), None)
        # AESGCM appends the 16-byte tag to ciphertext
        ciphertext = ct[:-16]
        tag = ct[-16:]
        return ciphertext, nonce, tag

    def decrypt(self, ciphertext: bytes, nonce: bytes, tag: bytes) -> str:
        """Decrypt ciphertext. Returns plaintext string."""
        ct_with_tag = ciphertext + tag
        return self._gcm.decrypt(nonce, ct_with_tag, None).decode()

    async def store(self, provider: str, key_name: str, value: str) -> None:
        """Encrypt and store a credential."""
        ciphertext, nonce, tag = self.encrypt(value)
        await self.db.execute(
            "INSERT OR REPLACE INTO credentials "
            "(provider, key_name, encrypted, nonce, tag) VALUES (?, ?, ?, ?, ?)",
            (provider, key_name, ciphertext, nonce, tag),
        )

    async def retrieve(self, provider: str, key_name: str) -> str | None:
        """Retrieve and decrypt a credential."""
        row = await self.db.fetchone(
            "SELECT encrypted, nonce, tag FROM credentials WHERE provider = ? AND key_name = ?",
            (provider, key_name),
        )
        if not row:
            return None
        return self.decrypt(row["encrypted"], row["nonce"], row["tag"])

    async def delete(self, provider: str, key_name: str) -> bool:
        """Delete a credential."""
        cursor = await self.db.execute(
            "DELETE FROM credentials WHERE provider = ? AND key_name = ?",
            (provider, key_name),
        )
        return cursor.rowcount > 0

    async def list_providers(self) -> list[dict]:
        """List all stored credential providers."""
        return await self.db.fetchall(
            "SELECT DISTINCT provider, key_name FROM credentials ORDER BY provider"
        )
