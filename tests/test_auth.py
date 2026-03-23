"""Regression tests for auth endpoints."""

import pytest


@pytest.mark.asyncio
async def test_get_me(client_a):
    resp = await client_a.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "parenta@test.com"
    assert data["role"] == "parent_a"
    assert data["display_name"] == "Parent A"


@pytest.mark.asyncio
async def test_get_me_parent_b(client_b):
    resp = await client_b.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "parentb@test.com"
    assert data["role"] == "parent_b"


@pytest.mark.asyncio
async def test_list_email_aliases_empty(client_a):
    resp = await client_a.get("/auth/me/emails")
    assert resp.status_code == 200
    data = resp.json()
    assert data["primary"] == "parenta@test.com"
    assert data["aliases"] == []


@pytest.mark.asyncio
async def test_add_and_list_email_alias(client_a):
    resp = await client_a.post("/auth/me/emails", json={"email": "alias@test.com"})
    assert resp.status_code == 200

    resp = await client_a.get("/auth/me/emails")
    assert resp.status_code == 200
    data = resp.json()
    assert "alias@test.com" in data["aliases"]


@pytest.mark.asyncio
async def test_delete_email_alias(client_a):
    await client_a.post("/auth/me/emails", json={"email": "todelete@test.com"})
    resp = await client_a.delete("/auth/me/emails/todelete@test.com")
    assert resp.status_code == 200

    resp = await client_a.get("/auth/me/emails")
    data = resp.json()
    assert "todelete@test.com" not in data["aliases"]
