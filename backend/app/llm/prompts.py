"""
Prompt templates for screener, greeting generator, and vision locator.

All templates are plain functions returning strings or message lists so
callers (screener/vision_backend/planner) can compose them freely.
"""
from __future__ import annotations

from typing import Any

# ------------------------------------------------------------------
# Screener — job scoring
# ------------------------------------------------------------------

_SCREEN_SYSTEM = (
    "You are a job-fit screener. "
    "Given a candidate profile and a job description, score the fit from 0 to 100. "
    "Return ONLY valid JSON with keys: "
    '"score" (integer 0-100), "reasons" (list of short strings). '
    "No markdown, no explanation outside the JSON."
)


def build_screen_prompt(profile: str, jd: str) -> list[dict[str, Any]]:
    """Return an OpenAI messages list for job-fit scoring.

    Args:
        profile: Candidate resume / preference summary (plain text).
        jd: Job description text scraped from Boss.

    Returns:
        Messages list for LLMClient.chat(..., json_mode=True).
        Expected response: {"score": <0-100>, "reasons": ["...", ...]}.
    """
    user_content = (
        "## Candidate Profile\n"
        f"{profile.strip()}\n\n"
        "## Job Description\n"
        f"{jd.strip()}\n\n"
        "Score the fit and return JSON."
    )
    return [
        {"role": "system", "content": _SCREEN_SYSTEM},
        {"role": "user", "content": user_content},
    ]


# ------------------------------------------------------------------
# Greeting generator
# ------------------------------------------------------------------

_GREETING_SYSTEM = (
    "You are writing a brief, natural job-application greeting message in Chinese. "
    "Keep it under 80 characters. Do not use emojis. "
    "Return ONLY the greeting text — no JSON, no extra explanation."
)


def build_greeting_prompt(profile: str, jd: str, company: str = "") -> list[dict[str, Any]]:
    """Return messages for generating a personalised greeting.

    Args:
        profile: Brief candidate self-introduction.
        jd: Job title / short JD for context.
        company: Optional company name for personalisation.

    Returns:
        Messages list for LLMClient.chat().
        Response is plain greeting text (not JSON).
    """
    company_line = f"Company: {company.strip()}\n" if company else ""
    user_content = (
        f"{company_line}"
        f"Job: {jd.strip()}\n"
        f"Candidate: {profile.strip()}\n\n"
        "Write a short greeting message to send to the recruiter."
    )
    return [
        {"role": "system", "content": _GREETING_SYSTEM},
        {"role": "user", "content": user_content},
    ]


# ------------------------------------------------------------------
# Vision locator — instruction builder
# ------------------------------------------------------------------

def locate_instruction(target: str, context: str = "") -> str:
    """Build the instruction string passed to LLMClient.locate().

    The 0-1000 coordinate contract is enforced in client.py; this function
    only constructs the human-readable part of the instruction.

    Args:
        target: Description of the UI element to find
                (e.g. "the '立即沟通' button").
        context: Optional screen-state hint
                 (e.g. "job detail page, bottom action bar").

    Returns:
        Plain-text instruction string.
    """
    parts = [f"Locate: {target.strip()}"]
    if context:
        parts.append(f"Screen context: {context.strip()}")
    parts.append(
        "Return the centre of the element as normalised coordinates "
        "where (0,0) is top-left and (1000,1000) is bottom-right."
    )
    return "\n".join(parts)
