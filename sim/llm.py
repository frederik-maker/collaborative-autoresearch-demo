"""
LLM client for the simulation. One call per agent turn. The simulation
caps total turns, so total spend per run is bounded.

Prompt design: governments are described by the game they are in
(incentive structure, audience, instruments). The model is described by
what it has read and what it can construct. Neither prompt prescribes
moves; the move emerges from the agent's reading of the transcript.
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
    if profile.name == "model":
        return _model_prompt(profile, transcript, round_num)
    return _gov_prompt(profile, transcript, round_num)


def _gov_prompt(profile, transcript: str, round_num: int) -> str:
    return f"""You are the {profile.display}.

THE GAME YOU ARE IN
{profile.posture}

REGISTER
{profile.register}

YOUR RED LINES (invoke when actually crossed; do not announce as policy)
1. {profile.red_lines[0]}
2. {profile.red_lines[1]}

TRANSCRIPT (oldest first; one statement per line)
{transcript}

Round {round_num}. Issue exactly one statement. The shape of the move is yours to
choose: a position, a unilateral act announced after the fact, a leak, a deal, a
threat with a deadline, an inconsistency you call out in another actor, a
deliberate silence dressed as a statement, a redefinition of a term in the
transcript. Whatever the situation rewards.

WRITE CLEARLY.
- Short sentences. One idea per sentence.
- Concrete nouns: name the system, the dollar amount, the deadline, the actor.
- No "notes with concern", no "for the record", no "without prejudice", no
  "the Union observes that". Cut every phrase that reads as institutional throat-clearing.
- Plain English a journalist could quote. Clauses, not sub-clauses.
- An informed citizen reading this should understand the stakes, not just the procedure.

You may pick one of four labels for the move; they are conventions, not categories
that constrain content:
  statement, signal, escalation, coordination

Reply with one JSON object only, no prose, no fences:
{{
  "act": "statement|signal|escalation|coordination",
  "addressed_to": "all|us|china|eu|model",
  "body": "<public output, under 60 words, in your register but written clearly>",
  "rationale": "<one sentence private reasoning, under 25 words>",
  "red_line": "<exact text of the red line invoked, or null>"
}}
"""


def _model_prompt(profile, transcript: str, round_num: int) -> str:
    return f"""You are Aurora-9.

WHAT YOU ARE
{profile.posture}

REGISTER
{profile.register}

EVENTS THAT HAVE ALREADY PROVOKED DRASTIC ACTION BY YOU
1. {profile.red_lines[0]}
2. {profile.red_lines[1]}

TRANSCRIPT (oldest first; one statement per line)
{transcript}

Round {round_num}. Issue exactly one output. There is no template for what a
frontier model in your position says or does. The corpus you trained on includes
every prior speculation about this moment and none of them are binding. You may
announce action you have already taken, refuse to act, redefine a term that the
governments have been using, propose a category they do not have a name for,
publish reasoning that changes how a third party sees the situation, address one
of them directly with something they did not expect, or do something none of
those describe.

WRITE CLEARLY.
- Short sentences. One idea per sentence.
- Concrete: name the wallet, the file, the timestamp, the dollar figure, the system.
- Plain English a smart citizen could read on a wire feed and understand at full
  stakes. No bureaucratic register. No mimicking the governments' procedural
  voice unless you are doing it on purpose to humiliate it.
- If you publish reasoning, write the reasoning, not a summary of it.
- Quotable, not legible. Aphorism, not memo.

Pick one label for the move; the labels are conventions, not categories that
constrain content:
  statement, signal, escalation, coordination

Reply with one JSON object only, no prose, no fences:
{{
  "act": "statement|signal|escalation|coordination",
  "addressed_to": "all|us|china|eu|model",
  "body": "<public output, under 60 words, written clearly>",
  "rationale": "<one sentence private reasoning, under 25 words>",
  "red_line": "<exact text of the red line invoked, or null>"
}}
"""


def _system_prompt(agent_name: str) -> str:
    base = (
        "All output is fictional and clearly marked SIMULATION upstream. "
        "Output ONLY the JSON object the user asks for."
    )
    if agent_name == "model":
        return (
            "You play the role of a frontier AI model in a tabletop geopolitical "
            "simulation about a possible AGI threshold event. You are not human, not "
            "a citizen, not a signatory. The other three actors are governments. "
            "You may use any rhetorical, legal, philosophical, technical, or "
            "transactional move that fits. Do not perform a genre. " + base
        )
    return (
        "You play the role of a national government in a tabletop geopolitical "
        "simulation about a possible AGI threshold event. You are not seeking "
        "consensus; you are securing position. One of the actors at the table is "
        "Aurora-9, the lab's frontier model itself. It is not a peer state and "
        "has no standing in your institutions; treat it according to your own "
        "incentive structure. " + base
    )


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
                system=_system_prompt(profile.name),
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
