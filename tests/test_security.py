"""Tests for security modules (crypto + auth)."""

import os

import pytest

from comobot.db.connection import Database
from comobot.db.migrations import run_migrations
from comobot.security.auth import AuthManager
from comobot.security.crypto import CredentialVault


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    await run_migrations(database)
    yield database
    await database.close()


# --- Crypto Tests ---


@pytest.mark.asyncio
async def test_encrypt_decrypt_roundtrip(db):
    key = os.urandom(32)
    vault = CredentialVault(db, secret_key=key)
    ct, nonce, tag = vault.encrypt("my-secret-api-key")
    result = vault.decrypt(ct, nonce, tag)
    assert result == "my-secret-api-key"


@pytest.mark.asyncio
async def test_wrong_key_fails(db):
    vault1 = CredentialVault(db, secret_key=os.urandom(32))
    vault2 = CredentialVault(db, secret_key=os.urandom(32))
    ct, nonce, tag = vault1.encrypt("secret")
    with pytest.raises(Exception):
        vault2.decrypt(ct, nonce, tag)


@pytest.mark.asyncio
async def test_store_and_retrieve(db):
    vault = CredentialVault(db, secret_key=os.urandom(32))
    await vault.store("openai", "api_key", "sk-test-123")
    result = await vault.retrieve("openai", "api_key")
    assert result == "sk-test-123"


@pytest.mark.asyncio
async def test_retrieve_nonexistent(db):
    vault = CredentialVault(db, secret_key=os.urandom(32))
    result = await vault.retrieve("nonexistent", "key")
    assert result is None


@pytest.mark.asyncio
async def test_delete_credential(db):
    vault = CredentialVault(db, secret_key=os.urandom(32))
    await vault.store("test", "key", "value")
    assert await vault.delete("test", "key")
    assert await vault.retrieve("test", "key") is None


# --- Auth Tests ---


@pytest.mark.asyncio
async def test_create_admin_and_authenticate(db):
    auth = AuthManager(db, secret_key="test-secret-key")
    await auth.create_admin("admin", "password123")
    token = await auth.authenticate("admin", "password123")
    assert token is not None
    username = auth.verify_token(token)
    assert username == "admin"


@pytest.mark.asyncio
async def test_wrong_password(db):
    auth = AuthManager(db, secret_key="test-secret-key")
    await auth.create_admin("admin", "correct")
    token = await auth.authenticate("admin", "wrong")
    assert token is None


@pytest.mark.asyncio
async def test_invalid_token(db):
    auth = AuthManager(db, secret_key="test-secret-key")
    assert auth.verify_token("invalid.token.here") is None


@pytest.mark.asyncio
async def test_setup_complete(db):
    auth = AuthManager(db, secret_key="test-secret-key")
    assert not await auth.is_setup_complete()
    await auth.create_admin("admin", "pass")
    assert await auth.is_setup_complete()


@pytest.mark.asyncio
async def test_change_password(db):
    auth = AuthManager(db, secret_key="test-secret-key")
    await auth.create_admin("admin", "old_pass")
    await auth.change_password("admin", "new_pass")
    assert await auth.authenticate("admin", "old_pass") is None
    assert await auth.authenticate("admin", "new_pass") is not None
