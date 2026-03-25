"""NaCl (X25519 + XSalsa20-Poly1305) encryption for mobile device communication."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import nacl.public
import nacl.secret
import nacl.utils


@dataclass
class NaClKeyPair:
    """X25519 key pair for ECDH key exchange."""

    public_key: bytes  # 32 bytes
    secret_key: bytes  # 32 bytes

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key).decode()

    @property
    def secret_key_b64(self) -> str:
        return base64.b64encode(self.secret_key).decode()

    @classmethod
    def from_b64(cls, public_b64: str, secret_b64: str) -> NaClKeyPair:
        return cls(
            public_key=base64.b64decode(public_b64),
            secret_key=base64.b64decode(secret_b64),
        )


def generate_keypair() -> NaClKeyPair:
    """Generate a new X25519 key pair."""
    private_key = nacl.public.PrivateKey.generate()
    return NaClKeyPair(
        public_key=bytes(private_key.public_key),
        secret_key=bytes(private_key),
    )


def compute_shared_key(our_secret: bytes, their_public: bytes) -> bytes:
    """Compute shared secret via X25519 ECDH.

    Returns a 32-byte shared key suitable for NaCl SecretBox.
    """
    our_private = nacl.public.PrivateKey(our_secret)
    their_pub = nacl.public.PublicKey(their_public)
    box = nacl.public.Box(our_private, their_pub)
    return box.shared_key()


def encrypt_message(plaintext: str, shared_key: bytes) -> str:
    """Encrypt a message using NaCl SecretBox (XSalsa20-Poly1305).

    Returns base64-encoded ciphertext (nonce prepended).
    """
    box = nacl.secret.SecretBox(shared_key)
    encrypted = box.encrypt(plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode()


def decrypt_message(ciphertext_b64: str, shared_key: bytes) -> str:
    """Decrypt a NaCl SecretBox message from base64.

    Expects nonce to be prepended to the ciphertext (standard NaCl format).
    """
    box = nacl.secret.SecretBox(shared_key)
    encrypted = base64.b64decode(ciphertext_b64)
    return box.decrypt(encrypted).decode("utf-8")


def encrypt_json(data: dict, shared_key: bytes) -> str:
    """Encrypt a JSON-serializable dict. Returns base64-encoded ciphertext."""
    return encrypt_message(json.dumps(data, ensure_ascii=False), shared_key)


def decrypt_json(ciphertext_b64: str, shared_key: bytes) -> dict:
    """Decrypt a base64-encoded ciphertext to a dict."""
    return json.loads(decrypt_message(ciphertext_b64, shared_key))
