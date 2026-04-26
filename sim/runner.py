"""
Per-agent runner. One Python process per agent, each connected to its own
AXL node. Agents do not coordinate directly: each polls its receive queue,
checks the shared turn counter, and acts when its own cooldown has elapsed.

Hard caps:
- Global: SIM_MAX_TURNS turns per simulation (default 20).
- Per agent: SIM_AGENT_COOLDOWN seconds between own turns (default 8).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import random
import time
from pathlib import Path

from .agents import PROFILES
from .axl import AxlNetwork, Statement
from .llm import call_agent

STATE_DIR = Path(os.environ.get("SIM_STATE_DIR", "state"))
TRANSCRIPT_PATH = STATE_DIR / "transcript.jsonl"
FLOW_PATH = STATE_DIR / "messages.jsonl"
COUNTER_PATH = STATE_DIR / "turns.json"
ERRORS_PATH = STATE_DIR / "errors.jsonl"

MAX_TURNS = int(os.environ.get("SIM_MAX_TURNS", "20"))
COOLDOWN = float(os.environ.get("SIM_AGENT_COOLDOWN", "8"))
INITIAL_OFFSETS = {"us": 0.0, "china": 2.0, "eu": 4.0, "model": 6.0}

log = logging.getLogger("runner")


def _read_state() -> tuple[int, bool]:
    """Return (turn_count, running). Default to (0, False) if file missing."""
    try:
        with COUNTER_PATH.open("r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return int(data.get("count", 0)), bool(data.get("running", False))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 0, False


def _claim_turn() -> int | None:
    """
    Atomically increment the global turn counter if under MAX_TURNS and
    the simulation is marked running. Returns the claimed turn number,
    or None if the cap is reached or the simulation is not running.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with COUNTER_PATH.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read()
            try:
                data = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                data = {}
            count = int(data.get("count", 0))
            running = bool(data.get("running", False))
            if not running or count >= MAX_TURNS:
                return None
            count += 1
            data["count"] = count
            f.seek(0)
            f.truncate()
            f.write(json.dumps(data))
            f.flush()
            return count
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _mark_not_running() -> None:
    """Flip the running flag to false. Idempotent and safe under concurrent calls."""
    if not COUNTER_PATH.exists():
        return
    with COUNTER_PATH.open("r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            try:
                data = json.loads(f.read() or "{}")
            except json.JSONDecodeError:
                data = {}
            if data.get("running"):
                data["running"] = False
                f.seek(0)
                f.truncate()
                f.write(json.dumps(data))
                f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record) + "\n"
    with path.open("a") as f:
        f.write(line)


def _wait_for_node(net: AxlNetwork, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        our = net.our_id()
        if our:
            peers = net.all_peer_ids()
            if peers:
                return True
        time.sleep(0.5)
    return bool(net.our_id())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", required=True, choices=list(PROFILES.keys()))
    p.add_argument("--api", required=True, help="AXL node HTTP API base URL")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{args.agent}] %(message)s",
    )

    profile = PROFILES[args.agent]
    net = AxlNetwork(api_url=args.api)

    log.info(f"waiting for AXL node and peers at {args.api}")
    if not _wait_for_node(net):
        log.warning("node never came up, exiting")
        return
    log.info(f"node ready, peers={len(net.all_peer_ids())}")

    transcript: list[Statement] = []
    last_acted = time.time() - COOLDOWN + INITIAL_OFFSETS.get(args.agent, 0.0)

    while True:
        for s in net.drain_recv_queue():
            transcript.append(s)

        count, running = _read_state()
        if not running:
            if count >= MAX_TURNS:
                log.info("simulation finished, exiting agent loop")
                return
            time.sleep(0.5)
            continue

        if count >= MAX_TURNS:
            _mark_not_running()
            log.info(f"turn cap reached ({count}/{MAX_TURNS}), exiting")
            return

        if time.time() - last_acted < COOLDOWN:
            time.sleep(0.4)
            continue

        turn = _claim_turn()
        if turn is None:
            time.sleep(0.5)
            continue

        lines = []
        for s in transcript[-24:]:
            tag = f"[{s.agent}->{s.addressed_to}]"
            extra = f" RED LINE: {s.red_line}" if s.red_line else ""
            lines.append(f"{tag} ({s.act}){extra} {s.body}")

        try:
            decision = call_agent(profile, lines, turn)
        except Exception as e:
            log.warning(f"LLM call failed on turn {turn}: {e}")
            _append_jsonl(ERRORS_PATH, {
                "ts": time.time(), "agent": args.agent,
                "turn": turn, "error": str(e),
            })
            last_acted = time.time()
            time.sleep(2)
            continue

        stmt = Statement(
            proto=1,
            round_num=turn,
            agent=args.agent,
            act=decision.act or "statement",
            addressed_to=decision.addressed_to or "all",
            body=decision.body,
            rationale=decision.rationale,
            red_line=decision.red_line,
            timestamp=time.time(),
        )
        sent = net.broadcast_statement(stmt)
        transcript.append(stmt)
        _append_jsonl(TRANSCRIPT_PATH, stmt.to_dict())
        _append_jsonl(FLOW_PATH, {
            "ts": stmt.timestamp,
            "turn": turn,
            "from": args.agent,
            "addressed_to": stmt.addressed_to,
            "act": stmt.act,
            "red_line": stmt.red_line,
            "peers_reached": sent,
            "peers_known": len(net.all_peer_ids()),
        })
        log.info(f"turn {turn} broadcast act={stmt.act} addressed_to={stmt.addressed_to} reached={sent}")
        last_acted = time.time() + random.uniform(0, 1.0)


if __name__ == "__main__":
    main()
