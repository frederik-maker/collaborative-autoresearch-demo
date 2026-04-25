"""
Web UI for the simulation. A single page with a Start button, the live
transcript, and the message-flow log. Polling-based: the page fetches
/api/state every ~1.5s and only pulls records added since the last call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from . import orchestrator
from .agents import PROFILES, SCENARIO, order

app = Flask(__name__)
app.jinja_env.auto_reload = True
app.config["TEMPLATES_AUTO_RELOAD"] = True

STATE_DIR = orchestrator.STATE_DIR
TRANSCRIPT_PATH = STATE_DIR / "transcript.jsonl"
FLOW_PATH = STATE_DIR / "messages.jsonl"
ERRORS_PATH = STATE_DIR / "errors.jsonl"

MAX_TURNS = int(os.environ.get("SIM_MAX_TURNS", "20"))


@app.route("/")
def index():
    profiles = [PROFILES[k] for k in order()]
    return render_template(
        "index.html",
        scenario=SCENARIO,
        profiles=profiles,
        max_turns=MAX_TURNS,
    )


@app.route("/api/start", methods=["POST"])
def api_start():
    return jsonify(orchestrator.start())


@app.route("/api/stop", methods=["POST"])
def api_stop():
    return jsonify(orchestrator.stop())


@app.route("/api/reset", methods=["POST"])
def api_reset():
    return jsonify(orchestrator.reset())


@app.route("/api/state")
def api_state():
    transcript_offset = int(request.args.get("transcript_offset", 0))
    flow_offset = int(request.args.get("flow_offset", 0))

    transcript, new_t_offset = orchestrator.read_jsonl(TRANSCRIPT_PATH, transcript_offset)
    flow, new_f_offset = orchestrator.read_jsonl(FLOW_PATH, flow_offset)
    errors, _ = orchestrator.read_jsonl(ERRORS_PATH, 0)

    st = orchestrator.status()

    return jsonify({
        "running": st["running"],
        "count": st["count"],
        "max_turns": MAX_TURNS,
        "alive_processes": len(st["alive"]),
        "expected_processes": 8,
        "transcript": transcript,
        "transcript_offset": new_t_offset,
        "flow": flow,
        "flow_offset": new_f_offset,
        "errors": errors[-5:] if errors else [],
    })


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
