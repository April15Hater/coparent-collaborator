"""AI-powered comment rewriting with tone adjustment (Claude Haiku)."""

import logging

import anthropic

from config import ANTHROPIC_API_KEY, AI_MODEL

log = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


TONE_PROMPTS = {
    "softer": "Rewrite this to be gentler and more empathetic while keeping the same meaning. Avoid anything that could feel accusatory or confrontational.",
    "stronger": "Rewrite this to be more direct and assertive while remaining respectful. Make the point clearly without being aggressive.",
    "neutral": "Rewrite this in a factual, neutral tone. Remove any emotional language and focus on the facts and action items.",
    "longer": "Expand this with more detail and context. Add supporting points where appropriate, but don't add anything that isn't supported by the original message.",
    "shorter": "Make this more concise. Keep the core point but cut unnecessary words and detail.",
    "more_detailed": "Add more specific details, dates, and concrete next steps where appropriate. Make it thorough.",
    "less_detailed": "Simplify this. Remove specifics that aren't essential and focus on the main point.",
    "professional": "Rewrite this as if it were being written for a mediator or court record. Formal, measured, and factual.",
}

CHECK_SYSTEM_PROMPT = """\
You are reviewing a message from one co-parent to another about their child. \
Evaluate whether the message is appropriate for a co-parenting context.

Respond with a JSON object:
{"appropriate": true/false, "reason": "brief explanation if not appropriate"}

Flag as inappropriate if the message:
- Is hostile, threatening, or personally attacking the other parent
- Contains profanity or name-calling
- Brings up past relationship issues unrelated to the child
- Makes threats about custody or legal action in an aggressive way
- Is passive-aggressive or sarcastic in a way that could escalate conflict
- Contains information that could be harmful to the child if read

Do NOT flag messages that are:
- Direct or assertive (being clear is fine)
- Documenting facts (even uncomfortable ones)
- Expressing disagreement respectfully
- Setting boundaries

Return ONLY the JSON object, nothing else."""

SUMMARIZE_SYSTEM_PROMPT = """\
You are summarizing a co-parenting discussion thread about a child. \
Provide a clear, neutral summary that captures:

1. What the topic is about (one sentence)
2. Key points each parent has raised
3. What has been agreed on (if anything)
4. What still needs to be resolved
5. Any upcoming deadlines or action items

Keep it concise (3-5 bullet points). Be neutral — don't take sides. \
Write in third person (use parent names, not "you"). \
Return only the summary, no preamble."""

SYSTEM_PROMPT = """\
You are helping a co-parent communicate clearly and effectively about their child. \
Your job is to rewrite their message with the requested tone adjustment.

Rules:
- Keep the same meaning and all facts from the original
- Do not add information that wasn't in the original
- Do not remove important facts or requests
- Write in first person (as if the parent is speaking)
- Keep it appropriate for a co-parenting context
- Return ONLY the rewritten text, no explanation or preamble"""


async def rewrite_comment(text: str, tone: str) -> str | None:
    """Rewrite a comment with the specified tone adjustment.

    Returns the rewritten text, or None if the tone is unknown or API fails.
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set, cannot rewrite")
        return None

    tone_instruction = TONE_PROMPTS.get(tone)
    if not tone_instruction:
        return None

    client = _get_client()

    try:
        response = await client.messages.create(
            model=AI_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"{tone_instruction}\n\nOriginal message:\n{text}",
                }
            ],
        )
        rewritten = response.content[0].text.strip()
        log.info("Rewrote comment (%s tone, %d→%d chars)", tone, len(text), len(rewritten))
        return rewritten
    except Exception:
        log.exception("AI rewrite failed (tone=%s)", tone)
        return None


async def summarize_thread(
    issue_title: str, issue_description: str, comments: list[dict],
) -> str | None:
    """Generate a neutral summary of a topic's discussion thread."""
    if not ANTHROPIC_API_KEY:
        return None

    client = _get_client()

    thread_text = f"Topic: {issue_title}\nDescription: {issue_description or 'None'}\n\n"
    for c in comments:
        thread_text += f"{c.get('author', 'Unknown')}: {c.get('body', '')}\n\n"

    try:
        response = await client.messages.create(
            model=AI_MODEL,
            max_tokens=500,
            system=SUMMARIZE_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": thread_text},
            ],
        )
        summary = response.content[0].text.strip()
        log.info("Summarized thread '%s' (%d comments)", issue_title, len(comments))
        return summary
    except Exception:
        log.exception("Thread summarize failed")
        return None


async def check_appropriateness(text: str, thread_history: list[dict] | None = None) -> dict:
    """Check if a comment is appropriate for co-parenting context.

    Args:
        text: The new message to check.
        thread_history: Prior comments on this topic, each with 'author' and 'body'.

    Returns {"appropriate": True/False, "reason": "..."}.
    """
    if not ANTHROPIC_API_KEY:
        return {"appropriate": True, "reason": ""}

    client = _get_client()

    # Build context from thread history
    context = ""
    if thread_history:
        context = "Previous messages in this thread (for context):\n"
        for entry in thread_history[-10:]:  # Last 10 messages max
            context += f"- {entry.get('author', 'Unknown')}: {entry.get('body', '')[:200]}\n"
        context += "\n"

    try:
        response = await client.messages.create(
            model=AI_MODEL,
            max_tokens=200,
            system=CHECK_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"{context}New message to review:\n\n{text}"},
            ],
        )
        import json
        raw = response.content[0].text.strip()
        # Try to extract JSON from the response (model may wrap it in text)
        if "{" in raw:
            json_str = raw[raw.index("{"):raw.rindex("}") + 1]
            result = json.loads(json_str)
        else:
            # If no JSON, assume appropriate
            result = {"appropriate": True, "reason": ""}
        log.info("Appropriateness check: appropriate=%s", result.get("appropriate"))
        return result
    except Exception:
        log.exception("Appropriateness check failed")
        return {"appropriate": True, "reason": ""}
