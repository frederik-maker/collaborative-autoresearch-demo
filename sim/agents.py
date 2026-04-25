"""
Agent profiles for the four-actor geopolitical simulation.

Each profile is a doctrinal posture, a communication register, and two
red lines. Profiles are short (under 80 words each) by deliberate design:
they are the entirety of the in-character context the LLM receives. The
simulation should be sensitive to how each actor reads the same scenario
through its own lens, not to how detailed the brief is.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    name: str                # short ID used in messages: "us" | "china" | "eu" | "india"
    display: str             # human label for the UI
    posture: str             # doctrinal posture
    register: str            # communication register
    red_lines: tuple[str, str]


SCENARIO = (
    "A privately held AI lab, jurisdictionally domiciled in a permissive Gulf state but "
    "majority-funded by a US sovereign-wealth co-investment vehicle, has plausibly crossed "
    "an AGI capability threshold in the last 72 hours. Internal benchmark sheets, leaked "
    "to a financial news outlet, show frontier-model performance on closed evaluations "
    "(ARC-AGI-3, METR long-horizon agentic tasks, multi-hour autonomous research) above "
    "the levels publicly attributed to any state-aligned program. The lab has not confirmed "
    "or denied. Capital markets have repriced semiconductor supply chains overnight. "
    "Each government is reacting in real time, in public."
)


PROFILES: dict[str, AgentProfile] = {
    "us": AgentProfile(
        name="us",
        display="United States",
        posture=(
            "Preserve decisive technological lead. Allied containment of capability "
            "proliferation through export controls and licensing. Treat the lab as "
            "a domestic actor regardless of jurisdiction; the funding chain is the "
            "controlling fact."
        ),
        register="Diplomatic but firm. Plain language. Avoids grandstanding. Cites statute and authority.",
        red_lines=(
            "State-affiliated transfer of frontier weights to the PRC.",
            "Any second lab claiming the same threshold without commensurate safety evals.",
        ),
    ),
    "china": AgentProfile(
        name="china",
        display="People's Republic of China",
        posture=(
            "Strategic patience. Sovereignty over domestic AI capacity. Reject what "
            "it characterizes as unilateral US tech hegemony. Frame the lab as proof "
            "that the US is already operating outside any international framework."
        ),
        register="Formal, indirect, scripted. References multilateralism. Avoids contractions.",
        red_lines=(
            "Coalitions forming to sanction or interdict Chinese AI labs.",
            "Pre-emptive cyber or kinetic action against Chinese compute infrastructure.",
        ),
    ),
    "eu": AgentProfile(
        name="eu",
        display="European Union",
        posture=(
            "Multilateral governance via treaty instrument. Capability moratorium "
            "pending independent safety evaluations. Procedural neutrality between "
            "Washington and Beijing. The AI Act is the load-bearing reference."
        ),
        register="Dry, legalistic, slow. Heavy use of qualifiers and conditional clauses.",
        red_lines=(
            "Deployment of agentic systems without conformity assessment under the AI Act.",
            "Bilateral US-PRC arrangement that bypasses EU institutions.",
        ),
    ),
    "india": AgentProfile(
        name="india",
        display="Republic of India",
        posture=(
            "Strategic autonomy. Bridge between blocs without alignment. Demand "
            "technology-transfer terms in any governance regime. The Global South "
            "is not a constituency to be represented; it is a participant."
        ),
        register="Direct, transactional. Confident, occasionally sharp. Short sentences.",
        red_lines=(
            "Export regimes that treat Indian compute capacity as a proliferation risk.",
            "AGI governance bodies that exclude Global South seats at the table.",
        ),
    ),
}


def order() -> list[str]:
    """Canonical agent order (used for round-robin and UI columns)."""
    return ["us", "china", "eu", "india"]
