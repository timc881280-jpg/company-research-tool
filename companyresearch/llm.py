"""Optional LLM extraction (Anthropic API). Reads the crawled page text and
returns the same schema as heuristics.run(). Enabled by ANTHROPIC_API_KEY."""
from __future__ import annotations

import json
import os
import re

import httpx

from .crawler import Page

MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-5-5")
MAX_CHARS = 150_000

PROMPT = """You are researching a company from the text of its own website.
Use ONLY the pages below. Never guess; use null / [] when the website does not say.

Return a single JSON object, no prose, with exactly this shape:
{
 "company": {"name": str|null, "description": str|null, "industry": str|null,
             "project_types": [str], "founded": str|null, "address": str|null},
 "employee_count": {"value": str|null, "basis": str},
 "people": [{"name": str, "title": str, "role_category": "owner|executive|vp|director|manager|other",
             "source": url}],
 "projects": {"stated_count": str|null, "listed_count": int,
              "current": [{"name": str, "type": str|null, "location": str|null,
                           "status": "current|completed|unknown", "summary": str, "url": url|null}]},
 "scope_of_work": [str],
 "notes": str
}
Rules: list EVERY person named on the site (owners, founders, C-suite, VPs, directors,
managers, staff). "listed_count" is how many distinct projects you actually found.
Mark status "current" only if the site says ongoing/under construction/in progress/upcoming.
For employee_count quote the evidence in "basis"; if only a team page exists, say the number
of people listed is a lower bound.

=== WEBSITE PAGES ===
"""


def run(pages: list[Page]) -> dict:
    key = os.environ["ANTHROPIC_API_KEY"]
    chunks, used = [], 0
    for p in pages:
        block = f"\n--- PAGE: {p.url}\n{p.text}\n"
        if used + len(block) > MAX_CHARS:
            block = block[: max(0, MAX_CHARS - used)]
        chunks.append(block)
        used += len(block)
        if used >= MAX_CHARS:
            break
    r = httpx.post(
        os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com") + "/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={"model": MODEL, "max_tokens": 8000,
              "messages": [{"role": "user", "content": PROMPT + "".join(chunks)}]},
        timeout=180)
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"])
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("LLM returned no JSON")
    return json.loads(m.group(0))
