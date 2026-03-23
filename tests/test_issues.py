"""Regression tests for issue CRUD endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_issues_empty(client_a):
    resp = await client_a.get("/api/issues")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_issue_parent_a(client_a):
    resp = await client_a.post("/api/issues", json={
        "title": "School Enrollment",
        "description": "Need to decide on school for next year.",
        "category": "education",
        "priority": "high",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "School Enrollment"
    assert data["status"] == "open"
    assert data["category"] == "education"
    assert data["priority"] == "high"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_issue_parent_b_forbidden(client_b):
    """parent_b must not be able to create issues."""
    resp = await client_b.post("/api/issues", json={
        "title": "Unauthorized",
        "description": "...",
        "category": "other",
        "priority": "normal",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_issue(client_a):
    create_resp = await client_a.post("/api/issues", json={
        "title": "Medical Checkup",
        "description": "Annual checkup due.",
        "category": "medical",
        "priority": "normal",
    })
    issue_id = create_resp.json()["id"]

    resp = await client_a.get(f"/api/issues/{issue_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == issue_id
    assert resp.json()["title"] == "Medical Checkup"


@pytest.mark.asyncio
async def test_get_issue_not_found(client_a):
    resp = await client_a.get("/api/issues/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_issues_after_create(client_a):
    await client_a.post("/api/issues", json={
        "title": "Topic 1", "description": "", "category": "other", "priority": "normal",
    })
    await client_a.post("/api/issues", json={
        "title": "Topic 2", "description": "", "category": "other", "priority": "normal",
    })
    resp = await client_a.get("/api/issues")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_update_issue_status_parent_a(client_a):
    create_resp = await client_a.post("/api/issues", json={
        "title": "Status Test", "description": "", "category": "other", "priority": "normal",
    })
    issue_id = create_resp.json()["id"]

    resp = await client_a.patch(f"/api/issues/{issue_id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_issue_close_parent_b_forbidden(client_a, client_b):
    """parent_b must not be able to close or resolve an issue."""
    create_resp = await client_a.post("/api/issues", json={
        "title": "Close Test", "description": "", "category": "other", "priority": "normal",
    })
    issue_id = create_resp.json()["id"]

    resp = await client_b.patch(f"/api/issues/{issue_id}", json={"status": "closed"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_priority_parent_b_allowed(client_a, client_b):
    """parent_b is allowed to update priority."""
    create_resp = await client_a.post("/api/issues", json={
        "title": "Priority Test", "description": "", "category": "other", "priority": "normal",
    })
    issue_id = create_resp.json()["id"]

    resp = await client_b.patch(f"/api/issues/{issue_id}", json={"priority": "urgent"})
    assert resp.status_code == 200
    assert resp.json()["priority"] == "urgent"


@pytest.mark.asyncio
async def test_list_issues_status_filter(client_a):
    await client_a.post("/api/issues", json={
        "title": "Open Topic", "description": "", "category": "other", "priority": "normal",
    })
    create_resp = await client_a.post("/api/issues", json={
        "title": "In Progress Topic", "description": "", "category": "other", "priority": "normal",
    })
    issue_id = create_resp.json()["id"]
    await client_a.patch(f"/api/issues/{issue_id}", json={"status": "in_progress"})

    resp = await client_a.get("/api/issues?status=in_progress")
    assert resp.status_code == 200
    issues = resp.json()
    assert len(issues) == 1
    assert issues[0]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_get_timeline_includes_status_change(client_a):
    create_resp = await client_a.post("/api/issues", json={
        "title": "Timeline Test", "description": "", "category": "other", "priority": "normal",
    })
    issue_id = create_resp.json()["id"]

    await client_a.patch(f"/api/issues/{issue_id}", json={"status": "in_progress"})

    resp = await client_a.get(f"/api/issues/{issue_id}/timeline")
    assert resp.status_code == 200
    entries = resp.json()
    types = [e["type"] for e in entries]
    assert "status_change" in types
