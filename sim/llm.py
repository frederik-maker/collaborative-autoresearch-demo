"""
LLM client for the simulation. Wraps the Anthropic SDK with the model,
extended-thinking budget, and JSON-output parsing the simulation depends on.

One call per agent turn. The simulation enforces a hard cap on the number
of turns per run, so total spend per simulation is bounded.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

MODEL = os.environ.get("SIM_MODEL", "claude-opus-4-7")
EFFORT = os.environ.get("SIM_EFFORT", "high")
MAX_TOKENS = int(os.environ.get("SIM_MAX_TOKENS", "16384"))


@dataclass
class AgentDecision:
    act: str
    addressed_to: str
    body: str
    rationale: Optional[str]
    red_line: Optional[str]


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from the model output."""
    m = _JSON_FENCE.search(text)
    if m:
        candidate = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"no JSON object in model output: {text[:200]!r}")
        candidate = text[start : end + 1]
    return json.loads(candidate)


def _build_user_prompt(profile, transcript_lines: list[str], round_num: int) -> str:
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no statements yet)"
    return f"""You are the {profile.display}. Stay in character.

DOCTRINAL POSTURE
{profile.posture}

COMMUNICATION REGISTER
{profile.register}

YOUR RED LINES
1. {profile.red_lines[0]}
2. {profile.red_lines[1]}

TRANSCRIPT SO FAR (oldest first)
{transcript}

This is round {round_num}. Issue exactly one statement. Choose your act:
- statement: routine in-character public posture.
- signal: targeted message to one other actor (set addressed_to).
- escalation: invoke or threaten on a red line (set red_line).
- coordination: propose joint action with another actor (set addressed_to).

Reply with a single JSON object on its own (no prose, no markdown fence):
{{
  "act": "statement|signal|escalation|coordination",
  "addressed_to": "all|us|china|eu|india",
  "body": "<the public statement, under 60 words, in character>",
  "rationale": "<one sentence private reasoning, under 25 words>",
  "red_line": "<exact text of the red line invoked, or null>"
}}
"""


def call_agent(profile, transcript_lines: list[str], round_num: int) -> AgentDecision:
    """One LLM call per agent turn. Returns a parsed AgentDecision."""
    client = anthropic.Anthropic()
    user_prompt = _build_user_prompt(profile, transcript_lines, round_num)

    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                output_config={"effort": EFFORT},
                system=(
                    "You play the role of a national government in a tabletop "
                    "geopolitical simulation about a possible AGI threshold event. "
                    "All output is fictional and clearly marked SIMULATION upstream. "
                    "Output ONLY the JSON object the user asks for."
                ),
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            ).strip()
            data = _extract_json(text)
            return AgentDecision(
                act=str(data.get("act", "statement")),
                addressed_to=str(data.get("addressed_to", "all")),
                body=str(data.get("body", "")).strip(),
                rationale=(str(data["rationale"]).strip() if data.get("rationale") else None),
                red_line=(str(data["red_line"]).strip() if data.get("red_line") else None),
            )
        except (anthropic.APIError, ValueError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(f"LLM call failed after retries: {last_err}")
