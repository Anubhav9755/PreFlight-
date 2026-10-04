"""
Thin wrapper around the Gemini API. Both the Diagnoser (root-cause
explanation) and the Fixer (fix rationale) call through this.

Requires GEMINI_API_KEY to be set in your environment (or a .env file
loaded by python-dotenv — see README).
"""

import os

from google import genai
from dotenv import load_dotenv

from common.config import LLM_MODEL

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to a .env file in the "
                "project root or export it in your shell."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def ask_claude(system_prompt: str, user_prompt: str, max_tokens: int = 600) -> str:
    """One-shot call: system prompt sets the role, user prompt carries the
    evidence. Returns plain text."""

    client = get_client()

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=f"{system_prompt}\n\n{user_prompt}",
        config={
            "max_output_tokens": max_tokens,
        },
    )

    return response.text.strip()