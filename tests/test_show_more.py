"""Regression tests for the Show more button in topic detail view.

The bug: the onclick handler relied on looking up the full body from
cachedTimeline by entry id, but TimelineEntry has no id field — so
the lookup always returned undefined, setting textContent to empty.

The fix: encode the full body in a data-full attribute on the
comment-body div using encodeURIComponent. The onclick reads it
directly — no lookups, no hidden elements, no sibling traversal.
"""

import re
from pathlib import Path

import pytest

TEMPLATE_PATH = Path(__file__).parent.parent / "app" / "templates" / "issue_detail.html"


def test_show_more_onclick_present():
    """The Show more link should still exist in the template."""
    content = TEMPLATE_PATH.read_text()
    assert "Show more" in content, "Show more link has been removed from the template"


def test_show_more_uses_data_attribute():
    """The full body must be stored in a data-full attribute."""
    content = TEMPLATE_PATH.read_text()
    assert "data-full" in content, (
        "Expected a data-full attribute on comment-body to store "
        "the full comment body for the Show more handler"
    )
    assert "encodeURIComponent" in content, (
        "Expected encodeURIComponent to safely encode the body "
        "for the data-full attribute"
    )
    assert "decodeURIComponent" in content, (
        "Expected decodeURIComponent in the onclick to decode "
        "the body from the data-full attribute"
    )


def test_show_more_does_not_use_id_lookup():
    """The Show more handler must not rely on cachedTimeline.find by id.

    TimelineEntry has no id field, so any id-based lookup will always
    return undefined.
    """
    content = TEMPLATE_PATH.read_text()
    bad_pattern = re.compile(r"cachedTimeline\.find.*?\.id")
    assert not bad_pattern.search(content), (
        "Found cachedTimeline.find by id in Show more handler — "
        "TimelineEntry has no id field so this always fails."
    )


@pytest.mark.asyncio
async def test_timeline_returns_long_comment_body(client_a):
    """Long comment bodies must be fully returned by the timeline API.

    The API must return the full body so the template can encode it
    into the data-full attribute for expansion.
    """
    # Create an issue
    resp = await client_a.post("/api/issues", json={
        "title": "Show More Test",
        "description": "desc",
        "category": "other",
        "priority": "normal",
    })
    assert resp.status_code == 201
    issue_id = resp.json()["id"]

    # Post a long comment (> 300 chars)
    long_body = "A" * 350
    resp = await client_a.post(f"/api/issues/{issue_id}/comments", json={"body": long_body})
    assert resp.status_code == 201

    # Timeline must return the full body, not a truncated version
    resp = await client_a.get(f"/api/issues/{issue_id}/timeline")
    assert resp.status_code == 200
    entries = resp.json()
    comment_entries = [e for e in entries if e["type"] == "comment"]
    assert len(comment_entries) == 1
    assert comment_entries[0]["body"] == long_body, (
        "Timeline API truncated the comment body — the Show more feature "
        "relies on the full body being available"
    )
