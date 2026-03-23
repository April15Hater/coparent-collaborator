"""Regression tests for the Show more button in topic detail view.

Approach: long comments render the FULL body text in the DOM with
inline max-height/overflow styles. A named showMore() function removes
the style constraints on click. The text is always in the DOM.
"""

from pathlib import Path

import pytest

TEMPLATE_PATH = Path(__file__).parent.parent / "app" / "templates" / "issue_detail.html"


def test_show_more_present():
    """The Show more element should exist in the template."""
    content = TEMPLATE_PATH.read_text()
    assert "Show more" in content


def test_show_more_function_defined():
    """A named showMore function should be defined."""
    content = TEMPLATE_PATH.read_text()
    assert "function showMore" in content


def test_full_body_always_rendered():
    """The full body must be rendered in the DOM, not truncated by JS."""
    content = TEMPLATE_PATH.read_text()
    assert "e.body.slice" not in content, (
        "Found e.body.slice — the full body should always be in the DOM"
    )


def test_show_more_does_not_use_id_lookup():
    """The Show more handler must not rely on cachedTimeline.find by id."""
    content = TEMPLATE_PATH.read_text()
    assert "cachedTimeline.find" not in content or ".id" not in content.split("cachedTimeline.find")[1][:50] if "cachedTimeline.find" in content else True


@pytest.mark.asyncio
async def test_timeline_returns_long_comment_body(client_a):
    """Long comment bodies must be fully returned by the timeline API."""
    resp = await client_a.post("/api/issues", json={
        "title": "Show More Test",
        "description": "desc",
        "category": "other",
        "priority": "normal",
    })
    assert resp.status_code == 201
    issue_id = resp.json()["id"]

    long_body = "A" * 350
    resp = await client_a.post(f"/api/issues/{issue_id}/comments", json={"body": long_body})
    assert resp.status_code == 201

    resp = await client_a.get(f"/api/issues/{issue_id}/timeline")
    assert resp.status_code == 200
    entries = resp.json()
    comment_entries = [e for e in entries if e["type"] == "comment"]
    assert len(comment_entries) == 1
    assert comment_entries[0]["body"] == long_body
