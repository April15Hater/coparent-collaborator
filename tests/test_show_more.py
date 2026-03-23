"""Regression tests for the Show more button in topic detail view.

Approach: long comments render the FULL body text in the DOM, with CSS
class 'comment-body-truncated' (max-height + overflow:hidden) to
visually clip them. 'Show more' just removes the class — no text
replacement, no lookups, no encoding. The text is always in the DOM.
"""

import re
from pathlib import Path

import pytest

TEMPLATE_PATH = Path(__file__).parent.parent / "app" / "templates" / "issue_detail.html"
BASE_PATH = Path(__file__).parent.parent / "app" / "templates" / "base.html"


def test_show_more_onclick_present():
    """The Show more link should still exist in the template."""
    content = TEMPLATE_PATH.read_text()
    assert "Show more" in content, "Show more link has been removed from the template"


def test_show_more_uses_css_truncation():
    """Long comments should use CSS class truncation, not JS text truncation."""
    content = TEMPLATE_PATH.read_text()
    assert "comment-body-truncated" in content, (
        "Expected 'comment-body-truncated' class for CSS-based truncation"
    )
    assert "classList.remove" in content, (
        "Expected classList.remove in the Show more onclick to reveal full text"
    )


def test_truncation_css_exists():
    """The CSS class for truncation must exist in base.html."""
    content = BASE_PATH.read_text()
    assert "comment-body-truncated" in content, (
        "Expected .comment-body-truncated CSS rule in base.html"
    )
    assert "max-height" in content, (
        "Expected max-height in the truncation CSS"
    )
    assert "overflow" in content, (
        "Expected overflow:hidden in the truncation CSS"
    )


def test_full_body_always_rendered():
    """The full body must be rendered in the DOM, not truncated by JS."""
    content = TEMPLATE_PATH.read_text()
    # Should NOT slice the body for display — full esc(e.body) should be in the div
    # The old pattern was: e.body.slice(0, 300)
    # With CSS truncation, we render esc(e.body) always
    assert "e.body.slice" not in content, (
        "Found e.body.slice — the full body should be rendered in the DOM "
        "and CSS should handle visual truncation"
    )


def test_show_more_does_not_use_id_lookup():
    """The Show more handler must not rely on cachedTimeline.find by id."""
    content = TEMPLATE_PATH.read_text()
    bad_pattern = re.compile(r"cachedTimeline\.find.*?\.id")
    assert not bad_pattern.search(content), (
        "Found cachedTimeline.find by id in Show more handler — "
        "TimelineEntry has no id field so this always fails."
    )


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
    assert comment_entries[0]["body"] == long_body, (
        "Timeline API truncated the comment body"
    )
