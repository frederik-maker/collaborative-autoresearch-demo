"""
Process orchestration for the simulation.

Spawns four AXL node processes (one per agent), waits for the mesh to
form, then spawns four agent runner processes. Tracks PIDs so the web
server can stop and reset cleanly.

The AXL binary is expected at $AXL_BIN (default: ./bin/axl). Run
`scripts/build_axl.sh` once to produce it.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .agents import order
from .axl import AxlNetwork

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("SIM_STATE_DIR", str(ROOT / "state")))
LOG_DIR = STATE_DIR / "logs"
PIDS_PATH = STATE_DIR / "pids.json"
COUNTER_PATH = STATE_DIR / "turns.json"
CONFIG_DIR = ROOT / "configs"
AXL_BIN = Path(os.environ.get("AXL_BIN", str(ROOT / "bin" / "axl")))

API_PORTS = {"us": 9002, "china": 9012, "eu": 9022, "model": 9032}
PEER_BOOTSTRAP_TIMEOUT = float(os.environ.get("SIM_PEER_TIMEOUT", "90"))


def _api_url(agent: str) -> str:
    return f"http://127.0.0.1:{API_PORTS[agent]}"


def _record_pids(pids: dict[str, int]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PIDS_PATH.write_text(json.dumps(pids))


def _read_pids() -> dict[str, int]:
    if not PIDS_PATH.exists():
        return {}
    try:
        return json.loads(PIDS_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _set_running(running: bool) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if COUNTER_PATH.exists():
        try:
            data = json.loads(COUNTER_PATH.read_text())
        except json.JSONDecodeError:
            data = {}
    data["running"] = running
    COUNTER_PATH.write_text(json.dumps(data))


def _reset_state() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("transcript.jsonl", "messages.jsonl", "errors.jsonl"):
        path = STATE_DIR / name
        if path.exists():
            path.unlink()
    COUNTER_PATH.write_text(json.dumps({"count": 0, "running": False}))


def _spawn_axl(agent: str) -> subprocess.Popen:
    cfg = CONFIG_DIR / f"{agent}.json"
    log = (LOG_DIR / f"axl-{agent}.log").open("a")
    env = os.environ.copy()
    proc = subprocess.Popen(
        [str(AXL_BIN), "-config", str(cfg)],
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env=env,
        start_new_session=True,
    )
    return proc


def _spawn_agent(agent: str) -> subprocess.Popen:
    log = (LOG_DIR / f"agent-{agent}.log").open("a")
    env = os.environ.copy()
    env.setdefault("SIM_STATE_DIR", str(STATE_DIR))
    proc = subprocess.Popen(
        [sys.executable, "-m", "sim.runner", "--agent", agent, "--api", _api_url(agent)],
        stdout=log,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
        env=env,
        start_new_session=True,
    )
    return proc


def _wait_for_mesh(timeout: float = PEER_BOOTSTRAP_TIMEOUT) -> bool:
    """
    Wait until every node sees at least one peer. Hub-and-spoke: the US
    node listens, the other three dial in. On success returns True.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok = True
        for agent in order():
            net = AxlNetwork(api_url=_api_url(agent))
            if not net.our_id() or not net.all_peer_ids():
                ok = False
                break
        if ok:
            return True
        time.sleep(0.5)
    return False


def status() -> dict:
    pids = _read_pids()
    running_pids = {k: v for k, v in pids.items() if _is_alive(v)}
    counter: dict = {}
    if COUNTER_PATH.exists():
        try:
            counter = json.loads(COUNTER_PATH.read_text())
        except json.JSONDecodeError:
            counter = {}
    return {
        "pids": pids,
        "alive": running_pids,
        "running": bool(counter.get("running", False)),
        "count": int(counter.get("count", 0)),
    }


def start() -> dict:
    """
    Start a fresh simulation: reset state, spawn AXL nodes, wait for the
    mesh to form, spawn agents, mark running. Returns status.
    """
    cur = status()
    if cur["alive"]:
        return {"ok": False, "error": "simulation already running", "status": cur}

    if not AXL_BIN.exists():
        return {
            "ok": False,
            "error": (
                f"AXL binary not found at {AXL_BIN}. "
                "Run scripts/build_axl.sh once to build it."
            ),
        }

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"ok": False, "error": "ANTHROPIC_API_KEY not set in environment"}

    _reset_state()

    pids: dict[str, int] = {}
    try:
        for agent in order():
            proc = _spawn_axl(agent)
            pids[f"axl-{agent}"] = proc.pid
        _record_pids(pids)

        mesh_ok = _wait_for_mesh()
        if not mesh_ok:
            _kill_all(pids)
            PIDS_PATH.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": "mesh failed to form within timeout (peer bootstrap)",
            }

        _set_running(True)

        for agent in order():
            proc = _spawn_agent(agent)
            pids[f"agent-{agent}"] = proc.pid
        _record_pids(pids)

        return {"ok": True, "status": status()}
    except Exception as e:
        _kill_all(pids)
        PIDS_PATH.unlink(missing_ok=True)
        _set_running(False)
        return {"ok": False, "error": f"start failed: {type(e).__name__}: {e}"}


def stop() -> dict:
    pids = _read_pids()
    _kill_all(pids)
    _set_running(False)
    PIDS_PATH.unlink(missing_ok=True)
    return {"ok": True}


def _kill_all(pids: dict[str, int]) -> None:
    for name, pid in pids.items():
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.5)
    for name, pid in pids.items():
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def reset() -> dict:
    """Stop and clear all state."""
    stop()
    _reset_state()
    return {"ok": True}


def read_jsonl(path: Path, since_offset: int = 0) -> tuple[list[dict], int]:
    """Read all records from a JSONL file. Returns (records, byte_offset)."""
    if not path.exists():
        return [], 0
    records: list[dict] = []
    with path.open("rb") as f:
        f.seek(since_offset)
        chunk = f.read()
        new_offset = since_offset + len(chunk)
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records, new_offset


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["start", "stop", "reset", "status"])
    args = p.parse_args()
    out = {"start": start, "stop": stop, "reset": reset, "status": status}[args.cmd]()
    print(json.dumps(out, indent=2))
