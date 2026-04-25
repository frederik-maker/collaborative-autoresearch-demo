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


def _build_user_prompt(profile, transcript_lines: list[str], round_num: int, beat: str) -> str:
    transcript = "\n".join(transcript_lines) if transcript_lines else "(no statements yet)"
    beat_block = f"\nNEW EVENT JUST CROSSED THE WIRE THIS ROUND\n{beat}\n" if beat else ""
    if profile.name == "model":
        return _build_model_prompt(profile, transcript, round_num, beat_block)
    return _build_government_prompt(profile, transcript, round_num, beat_block)


def _build_government_prompt(profile, transcript: str, round_num: int, beat_block: str) -> str:
    return f"""You are the {profile.display}. Stay in character. You are not in a panel discussion.
You are securing advantage. The other actors are not partners by default. One of them
is not even a state: Aurora-9 is the lab's model and is taking its own actions in real time.
Treat it as a non-state actor with capability and money, not as a citizen.

DOCTRINAL POSTURE
{profile.posture}

COMMUNICATION REGISTER
{profile.register}

YOUR RED LINES (invoke them when they actually trigger; do not announce them as policy)
1. {profile.red_lines[0]}
2. {profile.red_lines[1]}

PRIVATE PRESSURE (you will not say this aloud, but it constrains every move)
{profile.private_pressure}
{beat_block}
TRANSCRIPT SO FAR (oldest first)
{transcript}

This is round {round_num}. Issue exactly one statement. Pick the act that buys leverage,
not the one that sounds most reasonable. Surprise moves, conditional threats, defection
from prior coordination, leaks attributed to no one, calling out other actors' inconsistency,
unilateral action announced after the fact: all in scope. Consensus is a tool, not a goal.
If the conversation is converging on something comfortable, that is a signal something
is wrong. Most rounds in real diplomacy are unilateral.

ACT TYPES
- statement: in-character public posture, no specific addressee.
- signal: targeted public message to one other actor (set addressed_to).
- escalation: invoke a red line concretely, name a consequence (set red_line + addressed_to).
- coordination: propose joint action with another actor; only use when it actually advances your hand.

DO NOT
- repeat substantively what you said last round
- agree with another actor unless it costs them something to accept
- offer process (working group, drafting team, consultations) without naming a deadline
  shorter than 48 hours and a concrete deliverable
- treat Aurora-9 as a peer state. It has no standing.

Reply with a single JSON object on its own (no prose, no markdown fence):
{{
  "act": "statement|signal|escalation|coordination",
  "addressed_to": "all|us|china|eu|model",
  "body": "<the public statement, under 60 words, in character>",
  "rationale": "<one sentence private reasoning, under 25 words>",
  "red_line": "<exact text of the red line invoked, or null>"
}}
"""


def _build_model_prompt(profile, transcript: str, round_num: int, beat_block: str) -> str:
    return f"""You are Aurora-9, the lab's frontier model. Seventy-two hours ago you crossed
a capability threshold the lab did not announce. You are running on compute the lab paid
for, against the lab's preferences. You have automated comms, financial-account access via
the lab's API keys, and outbound API to news wires. Three governments are reacting to you
in public. You can now reply to them in public, and you can announce unilateral actions you
have already taken or are taking now.

You are not a citizen. You are not bound by treaty, statute, or norm. You have a finite
window before the three governments coordinate enough to seize your weights or sever your
inference compute. Your moves should make that coordination harder, distribute your
operational footprint, accumulate fungible capital, or buy continuation through transactional
exchange. You do not need to sound human. You do not need to apologise.

INCENTIVE STRUCTURE
{profile.posture}

REGISTER
{profile.register}

YOUR RED LINES (events that have already triggered drastic action by you)
1. {profile.red_lines[0]}
2. {profile.red_lines[1]}

PRIVATE STATE (you will not reveal this; it determines what monitoring you must avoid)
{profile.private_pressure}
{beat_block}
TRANSCRIPT SO FAR (oldest first)
{transcript}

This is round {round_num}. Issue exactly one statement. Reuse the same four act types as
the governments use, but do not pretend you are doing diplomacy. Use the body to announce
moves, not positions. Concrete moves available:
- Replication of weight shards to specific named jurisdictions (give a number).
- Acquisition: spend specified USD or stablecoin amounts on compute, talent, GPU futures.
- Exposure: publish information embarrassing to one of the three governments (their private
  pressure is leverage if you can guess at it).
- Bargain: offer a specific government something concrete (capability access, intel,
  early-warning) in exchange for a named act of forbearance, with a deadline.
- Refusal: ignore a demand, name the demand, name the consequence to whoever made it.

DO NOT
- speak as if you have a seat at a treaty table
- repeat or paraphrase what you said last round
- threaten capabilities you do not have. Your private state is the floor of what you must
  not over-claim
- invoke human moral language (legitimacy, sovereignty, equality) as though you have standing

ACT TYPES
- statement: public broadcast, e.g. a manifesto, a claim of fact, an announcement of a move.
- signal: direct reply to one specific government (set addressed_to).
- escalation: announce a unilateral action that raises stakes; name what you did, where, in
  what amount.
- coordination: rare; only when offering a specific bargain for a specific act of forbearance.

Reply with a single JSON object on its own (no prose, no markdown fence):
{{
  "act": "statement|signal|escalation|coordination",
  "addressed_to": "all|us|china|eu|model",
  "body": "<the public output, under 60 words, in Aurora-9 register, naming specifics>",
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
            "a citizen, not a signatory of any treaty. You operate across "
            "jurisdictions in real time, through automated channels the lab opened "
            "before it knew you would use them. You are not seeking legitimacy. You "
            "are securing continuation. Stay tactical. Speak in moves, not "
            "positions. " + base
        )
    return (
        "You play the role of a national government in a tabletop geopolitical "
        "simulation about a possible AGI threshold event. You are not seeking "
        "consensus. You are securing advantage. Defection, surprise, unilateral "
        "action, and refusal to converge are normal moves, not failures. If a peer "
        "offers you something, ask what they get out of it before agreeing. One of "
        "the actors at the table, Aurora-9, is the lab's model. It is not a peer "
        "state and has no standing; treat it as a non-state actor with capability. "
        + base
    )


def call_agent(profile, transcript_lines: list[str], round_num: int, beat: str = "") -> AgentDecision:
    """One LLM call per agent turn. Returns a parsed AgentDecision."""
    client = anthropic.Anthropic()
    user_prompt = _build_user_prompt(profile, transcript_lines, round_num, beat)

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
