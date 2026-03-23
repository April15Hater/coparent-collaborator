"""Regression tests for issue #17 — Show more button in topic view.

The bug: onclick used `x.id==='${e.id}'` (string comparison) so the
cachedTimeline.find() always returned undefined, emptying the text body
instead of expanding it.

The fix: changed to `x.id===${e.id}` (no quotes) so the numeric id
from cachedTimeline matches correctly.
"""

import re
from pathlib import Path

import pytest

TEMPLATE_PATH = Path(__file__).parent.parent / "app" / "templates" / "issue_detail.html"


def test_show_more_uses_numeric_id_comparison():
    """The Show more onclick must compare id without string quotes."""
    content = TEMPLATE_PATH.read_text()
    # Bad pattern: id compared to a quoted template string e.g. x.id==='123'
    bad_pattern = re.compile(r"x\.id==='\$\{e\.id\}'")
    assert not bad_pattern.search(content), (
        "Found `x.id==='${e.id}'` — this compares a number to a string and "
        "always returns false, emptying the message body. Remove the quotes."
    )


def test_show_more_onclick_present():
    """The Show more link should still exist in the template."""
    content = TEMPLATE_PATH.read_text()
    assert "Show more" in content, "Show more link has been removed from the template"


def test_show_more_onclick_finds_entry():
    """The onclick must use cachedTimeline.find with a valid id expression."""
    content = TEMPLATE_PATH.read_text()
    # Correct pattern: numeric comparison x.id===${e.id}
    good_pattern = re.compile(r"x\.id===\$\{e\.id\}")
    assert good_pattern.search(content), (
        "Expected `x.id===${e.id}` (no quotes around the id) in the "
        "Show more onclick handler"
    )


@pytest.mark.asyncio
async def test_timeline_returns_long_comment_body(client_a):
    """Long comment bodies must be fully returned by the timeline API.

    This validates the server-side data that feeds the Show more JS fix —
    the API must return the full body so the onclick handler can expand it.
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
    comment_id = resp.json()["id"]

    # Timeline must return the full body, not a truncated version
    resp = await client_a.get(f"/api/issues/{issue_id}/timeline")
    assert resp.status_code == 200
    entries = resp.json()
    comment_entries = [e for e in entries if e["type"] == "comment"]
    assert len(comment_entries) == 1
    assert comment_entries[0]["body"] == long_body, (
        "Timeline API truncated the comment body — the Show more JS "
        "expansion relies on the full body being in cachedTimeline"
    )
