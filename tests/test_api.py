"""Tests for FastAPI endpoints."""

import os

import pytest
from fastapi.testclient import TestClient

from comobot.api.app import create_app
from comobot.db.connection import Database
from comobot.db.migrations import run_migrations
from comobot.security.auth import AuthManager
from comobot.security.crypto import CredentialVault


@pytest.fixture
async def app(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.connect()
    await run_migrations(db)
    vault = CredentialVault(db, secret_key=os.urandom(32))
    auth = AuthManager(db, secret_key="test-jwt-secret")
    application = create_app(db=db, vault=vault, auth=auth)
    yield application
    await db.close()


@pytest.fixture
def client(app):
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_setup_status_not_complete(client):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json()["setup_complete"] is False


def test_setup_flow(client):
    resp = client.post(
        "/api/setup",
        json={
            "admin_password": "securepassword123",
            "provider": "openai",
            "api_key": "sk-test-key",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Setup already done
    resp = client.post("/api/setup", json={"admin_password": "another"})
    assert resp.status_code == 400


def test_setup_short_password(client):
    resp = client.post("/api/setup", json={"admin_password": "short"})
    assert resp.status_code == 400


def test_login_flow(client):
    # Setup first
    client.post("/api/setup", json={"admin_password": "securepassword123"})

    # Login
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "securepassword123",
        },
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token

    # Wrong password
    resp = client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "wrongpassword",
        },
    )
    assert resp.status_code == 401


def test_protected_endpoint_without_token(client):
    # /api/auth/refresh requires auth
    resp = client.post("/api/auth/refresh")
    assert resp.status_code == 401
