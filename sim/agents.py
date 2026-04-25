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
    private_pressure: str    # hidden friction the agent will not say aloud


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
        private_pressure=(
            "A sitting senator on the intelligence committee holds undisclosed equity "
            "in the lab through a Cayman LP. If exposed, the domestic-actor framing "
            "collapses and the licensing case turns into self-dealing."
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
        private_pressure=(
            "Two of the lab's lead researchers are PRC nationals on US visas, one "
            "on retainer to a Beijing-funded foundation. Public attack on the lab "
            "burns those assets. Quiet exfiltration is in motion and not yet complete."
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
        private_pressure=(
            "The EU's designated AI Act notified-body for frontier evaluation is a "
            "French consultancy whose principal sits on the lab's safety advisory "
            "board. Disclosure is days away. The treaty-grade framing collapses if "
            "the conformity infrastructure looks captured."
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
        private_pressure=(
            "Three weeks ago an Indian state-backed AI mission was shown the same "
            "benchmarks under NDA and signed a non-binding letter of intent for "
            "co-deployment. Outrage in public while quietly party to the program."
        ),
    ),
}


# Exogenous events injected at fixed turns. Each one is meant to disrupt the
# current trajectory: invalidate a frame, force a re-evaluation, raise stakes.
SCENARIO_BEATS: dict[int, str] = {
    5: (
        "WIRE: The lab issues a four-paragraph statement denying the leaked "
        "benchmarks are genuine, calls them 'adversarial AI-generated artefacts,' "
        "and threatens criminal referral against the news outlet. CEO unreachable. "
        "The lab's general counsel cancels a scheduled congressional briefing."
    ),
    9: (
        "WIRE: A pre-print appears on arXiv from a named former safety lead at the "
        "lab, posted from a personal account. It describes a kill-switch protocol "
        "the lab declined to ship and includes evaluation logs that match the "
        "leaked numbers within rounding. The author's bio on the lab site has been "
        "deleted in the last hour."
    ),
    13: (
        "WIRE: PRC Ministry of State Security announces detention of two foreign "
        "nationals at a Shenzhen datacenter on espionage charges. The foreign "
        "ministry confirms they were 'providing technical advisory services' to a "
        "domestic AI cooperative. Names withheld pending consular notification."
    ),
    17: (
        "WIRE: US Treasury OFAC announces overnight blocking sanctions on the "
        "Gulf sovereign-wealth fund's US-domiciled holdings, effective immediately, "
        "citing 'unauthorised dual-use technology investment.' Trading halted in "
        "the fund's commercial paper. Allies not pre-notified."
    ),
}


def beat_for_turn(turn: int) -> str:
    """Most recent unconsumed scenario beat at or before this turn."""
    return SCENARIO_BEATS.get(turn, "")


def order() -> list[str]:
    """Canonical agent order (used for round-robin and UI columns)."""
    return ["us", "china", "eu", "india"]
