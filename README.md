# AGI Threshold Sim

Four-agent geopolitical simulation built on the AXL P2P mesh.
Forked from [gensyn-ai/collaborative-autoresearch-demo](https://github.com/gensyn-ai/collaborative-autoresearch-demo).
Every output is fictional and watermarked SIMULATION.

## What it does

A privately held AI lab plausibly crosses an AGI capability threshold.
Leaked benchmarks circulate. Four governments, each running as a separate
AXL node on `127.0.0.1`, react in real time, coordinate or defect, and
issue public statements. There is no central coordinator. Each agent
sees only what its own AXL node receives, and decides independently
when to speak, what to say, and which red lines to invoke.

The four agents are United States, China, European Union, India. Each is
defined by a doctrinal posture, a communication register, and two red
lines, all under 80 words total. See `sim/agents.py`.

## Diff from the fork

The fork's transport layer is preserved verbatim. The application layer
is replaced.

| File | What changed |
|------|--------------|
| `skills/autoresearch-network/research_network.py` | Renamed and moved to `sim/axl.py`. HTTP plumbing for `/topology`, `/send`, `/recv` is unchanged. The `Finding` dataclass (val_bpb, train_py) is replaced with `Statement` (agent, act, addressed_to, body, red_line). The `ResearchNetwork` class is renamed `AxlNetwork`; ML-specific helpers (`should_adopt`, `best_peer_finding`, `write_train_py`) are removed. |
| `skills/autoresearch-network/SKILL.md` | Removed. The original used Claude Code skills to invoke the network from inside an agent session. The new code calls the Anthropic API directly from a Python loop, so a Claude Code skill is no longer the integration surface. |
| `train.py`, `prepare.py`, `program.md` | Removed. The research task and its 5-minute training loop are gone. |
| `pyproject.toml` | Stripped to two runtime dependencies: `anthropic` for the LLM call, `flask` for the web UI. |
| `sim/agents.py` | New. Four `AgentProfile` records (posture, register, two red lines) plus the shared scenario text. |
| `sim/llm.py` | New. Anthropic Claude Opus 4.7 client with extended thinking enabled. Returns a parsed `AgentDecision` per call. |
| `sim/runner.py` | New. The per-agent loop that replaces the original `LOOP FOREVER` from `program.md`: drain queue, claim a turn under file lock, call the LLM, broadcast, sleep. |
| `sim/orchestrator.py` | New. Spawns four AXL nodes plus four agent runner processes. Tracks PIDs, kills on reset. |
| `sim/server.py`, `sim/templates/index.html` | New. Flask web UI with a Start button, live transcript, message-flow log, and SIMULATION watermark. Polls `/api/state` every 1.5s. |
| `configs/{us,china,eu,india}.json` | New. One AXL node config per agent. Unique `api_port`, shared `tcp_port=7000` (each AXL node has an isolated gVisor netstack). US is the listener; the other three dial in. |
| `scripts/build_axl.sh`, `scripts/run_local.sh` | New. AXL is not vendored; the script clones and builds on demand into `bin/axl`. |
| `Dockerfile`, `railway.json` | New. Two-stage image: Go build for AXL, Python runtime for the web UI. |

The git history makes the rename of `research_network.py` to `sim/axl.py`
explicit, and the diff against `main` keeps the message-passing primitive
recognisable.

## AXL primitives used

The simulation relies on three endpoints that the AXL node exposes on
`http://127.0.0.1:<api_port>`:

- `GET /topology` returns this node's public key and every node it can
  reach. We combine `peers[]` (direct TLS neighbours) and `tree[]` (the
  full Yggdrasil spanning tree) to enumerate broadcast targets.
- `POST /send` with header `X-Destination-Peer-Id` sends a JSON Statement
  to one peer. The body is opaque bytes; the receiver decides how to
  parse them.
- `GET /recv` drains this node's inbound queue. Returns one Statement at
  a time as a 200 with `X-From-Peer-Id`, or 204 when empty.

Each agent's runner calls `drain_recv_queue()` to update its local view
of the conversation, builds a prompt that includes its own profile and
the recent transcript, and on its turn calls `broadcast_statement()` to
fan out to every reachable peer.

## Bounds and rate limits

These caps are hard, not configurable from the UI:

- `SIM_MAX_TURNS=20`. After 20 statements have been broadcast across all
  four agents combined, every runner exits. The counter lives in
  `state/turns.json` and is incremented under `fcntl` lock.
- `SIM_AGENT_COOLDOWN=8`. Each agent waits at least 8 seconds between
  its own broadcasts. Initial offsets stagger the first round so the
  conversation does not start as a simultaneous shout.
- One Anthropic call per agent turn. Extended thinking is capped at
  `SIM_THINKING_BUDGET=4096` tokens, output at `SIM_MAX_TOKENS=6144`.

A full simulation produces 20 LLM calls. Total spend per run is bounded
to a few dollars on Opus 4.7.

## Running locally

Requires Go 1.25+, Python 3.10+, and `uv`.

```bash
./scripts/build_axl.sh         # one-time: clones gensyn-ai/axl, builds bin/axl
export ANTHROPIC_API_KEY=sk-ant-...
./scripts/run_local.sh         # uv sync + start the web UI on :8080
```

Then open http://127.0.0.1:8080 and click **Start Simulation**. The
orchestrator spawns the four AXL nodes, waits for the mesh to form,
and starts the four agent processes. The transcript and flow log
update as statements are broadcast. **Stop and Reset** kills every
process and clears `state/`.

## Deploying to Railway

The repo includes a `Dockerfile` and `railway.json`. Push to a GitHub
repo connected to a Railway service and add `ANTHROPIC_API_KEY` to the
service environment. Railway provides `PORT` automatically; the web UI
binds to it. Click Start in the deployed UI to run a simulation; the
container holds the AXL nodes for the duration of the simulation only.

## Honest friction

The transport works exactly as the original autoresearch demo claimed,
but the message-bus model wants asynchronous one-shot agents and the
geopolitical simulation wants something closer to a turn-taking
deliberation. The compromise here is a global counter file plus a
per-agent cooldown, which keeps the cap honest and the pacing watchable
but means agents occasionally pile statements on top of each other or
react to a peer message they only learn about a turn later. A real
deliberation would model this as an explicit speaking-floor protocol on
top of AXL, not a pacing hack. Pricing-wise, Opus 4.7 with extended
thinking is overkill for 60-word statements; Sonnet would produce a
cheaper and equally readable run, but capability scaling on
red-line judgement was the explicit ask, so Opus stays the default.
