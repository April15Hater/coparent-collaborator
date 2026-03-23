"""Regression tests for issue #17 — Show more button in topic view.

The original bug: onclick relied on cachedTimeline.find(x=>x.id===...)
to look up the full body, but TimelineEntry has no `id` field, so the
find always returned undefined, emptying the text body instead of
expanding it.

The fix: store the full body in a hidden <span class="full-body"> sibling
so the onclick reads it directly from the DOM — no ID lookup needed.
"""

import re
from pathlib import Path

import pytest

TEMPLATE_PATH = Path(__file__).parent.parent / "app" / "templates" / "issue_detail.html"


def test_show_more_onclick_present():
    """The Show more link should still exist in the template."""
    content = TEMPLATE_PATH.read_text()
    assert "Show more" in content, "Show more link has been removed from the template"


def test_show_more_uses_hidden_full_body():
    """The Show more approach should store full body in a hidden span."""
    content = TEMPLATE_PATH.read_text()
    assert 'class="full-body"' in content, (
        "Expected a hidden span with class 'full-body' to store the "
        "complete comment body for the Show more handler"
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
        "TimelineEntry has no id field so this always fails. "
        "Use the hidden full-body span instead."
    )


@pytest.mark.asyncio
async def test_timeline_returns_long_comment_body(client_a):
    """Long comment bodies must be fully returned by the timeline API.

    This validates the server-side data that feeds the Show more feature —
    the API must return the full body so the template can render it into
    the hidden span for expansion.
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
