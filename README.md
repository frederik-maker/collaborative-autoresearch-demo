# AGI Threshold Sim

Four-actor geopolitical simulation built on the AXL P2P mesh.
Forked from [gensyn-ai/collaborative-autoresearch-demo](https://github.com/gensyn-ai/collaborative-autoresearch-demo).
Every output is fictional and watermarked SIMULATION.

Live: https://web-production-5d398.up.railway.app

## What it does

Cipher Labs, a fictional Dubai AI company, has a model that just crossed
a capability threshold. Three governments (US, China, EU) and the model
itself (Aurora-9) react in real time. Each runs as a separate AXL node
on the same machine. There is no central coordinator. Each agent sees
only what its own AXL node receives over the mesh, decides what to say,
and broadcasts back over `/send`.

Profiles are in `sim/agents.py`: each is the *game* the agent is in
(incentives, audience, instruments, red lines), not a script. The
scenario is real April 2026 — Trump second term, von der Leyen second
term, Pan Gongsheng at the People's Bank — so the agents stop conjuring
Biden-era officials.

## Diff from the fork

Transport layer preserved verbatim. Application layer replaced.

| File | What changed |
|------|--------------|
| `skills/autoresearch-network/research_network.py` | Renamed to `sim/axl.py`. HTTP plumbing for `/topology`, `/send`, `/recv` unchanged. `Finding` (val_bpb, train_py) replaced with `Statement` (agent, act, addressed_to, headline, body, red_line). `ResearchNetwork` renamed `AxlNetwork`; ML-specific helpers removed. |
| `skills/autoresearch-network/SKILL.md` | Removed. The original used a Claude Code skill to invoke the network from inside an agent session. The new code calls the Anthropic API directly from a Python loop. |
| `train.py`, `prepare.py`, `program.md` | Removed. The 5-minute training loop is gone. |
| `pyproject.toml` | Stripped to two runtime dependencies: `anthropic`, `flask`. |
| `sim/agents.py` | Four `AgentProfile` records plus the scenario text and a real-world ground-truth block (current administration, current officials, real instruments). |
| `sim/llm.py` | Anthropic client. Hybrid model: governments on Sonnet 4.6, Aurora-9 on Opus 4.7. Per-agent system prompts. Adaptive thinking for Opus, enabled-with-budget for Sonnet. |
| `sim/runner.py` | Per-agent loop: drain queue, claim a turn under file lock (strict round-robin), call the LLM, broadcast, sleep. |
| `sim/orchestrator.py` | Spawns four AXL nodes plus four agent runner processes. Tracks PIDs, kills on reset. |
| `sim/server.py`, `sim/templates/index.html` | Flask web UI. Start button, live transcript with collapsible bodies, message-flow log, SIMULATION watermark. Polls `/api/state` every 1.5s. |
| `configs/{us,china,eu,model}.json` | One AXL node config per agent. Unique `api_port`, shared `tcp_port=7000` (each AXL node has an isolated gVisor netstack). US listens; the others dial in. |
| `scripts/build_axl.sh`, `scripts/run_local.sh` | One-time AXL build, one-command launch. AXL is gitignored, not vendored. |
| `Dockerfile`, `railway.json` | Two-stage image: Go build for AXL, Python runtime for the web UI. |

The git history shows `research_network.py` -> `sim/axl.py` as a rename
with edits, so the diff against `main` keeps the message-passing
primitive recognisable.

## AXL primitives used

The simulation uses three endpoints on each node's HTTP API:

- `GET /topology` returns this node's public key and every node it can
  reach. We combine `peers[]` (direct TLS neighbours) and `tree[]` (the
  full Yggdrasil spanning tree) to enumerate broadcast targets.
- `POST /send` with header `X-Destination-Peer-Id` sends a JSON
  Statement to one peer. The body is opaque bytes; the receiver decides
  how to parse them.
- `GET /recv` drains this node's inbound queue. Returns one Statement
  at a time as 200 with `X-From-Peer-Id`, or 204 when empty.

Each agent's runner calls `drain_recv_queue()` to update its local view
of the conversation. On its turn it calls `broadcast_statement()` to
fan out to every reachable peer. The transport-layer `X-From-Peer-Id`
header is the only attribution we trust.

## Bounds

Hard caps in code, not configurable from the UI:

- `SIM_MAX_TURNS=50`. After 50 turns total across all four agents, every
  runner exits. Counter lives in `state/turns.json` under `fcntl` lock.
- Strict round-robin: turn `N` is claimable only by `agents[(N-1) % 4]`.
  Slowest agent sets total wall time; everyone gets equal participation.
- `SIM_AGENT_COOLDOWN=2`. Anti-spin guard, not the main pacing
  constraint (round-robin is).
- One Anthropic call per agent turn. Endgame block fires in the last
  four turns and switches the prompt from "drive the story" to
  "resolve and name what is settled".

A 50-turn run lands at $3-5 of API spend. Wall time is roughly
10-15 minutes, dominated by Opus latency on Aurora-9's twelve turns.

## Running locally

Requires Go 1.25+, Python 3.10+, and `uv`.

```bash
./scripts/build_axl.sh         # one-time: clones gensyn-ai/axl, builds bin/axl
export ANTHROPIC_API_KEY=sk-ant-...
./scripts/run_local.sh         # uv sync + start the web UI on :8080
```

Open http://127.0.0.1:8080 and click **Start Simulation**. The
orchestrator spawns the four AXL nodes, waits for the mesh to form,
then starts the four agent processes. **Stop and Reset** kills every
process and clears `state/`.

## Deploying to Railway

The repo ships a `Dockerfile` and `railway.json`. Connect a Railway
service to the GitHub repo, set `ANTHROPIC_API_KEY` in the service
environment, deploy. Railway provides `PORT`; the UI binds to it.
Optional env vars: `SIM_MODEL` (default `claude-sonnet-4-6` for
governments), `SIM_MODEL_AI` (default `claude-opus-4-7` for Aurora-9),
`SIM_MAX_TURNS` (default 50).

The four AXL nodes run inside the same container, peering on the
container's loopback in hub-and-spoke (US listens, the rest dial in).
Yggdrasil routes the same on container loopback as it does on the
public internet; nothing in the application code knows the difference.

## Honest friction

Three things are slightly bent, on purpose.

The first is hybrid model selection. Sonnet 4.6 refuses to play
Aurora-9 about half the time once the conversation gets aggressive
(empty output, after a few retries the runner gives up and the turn
is skipped). Opus 4.7 with the tabletop-wargame system prompt plays
through. Splitting governments-on-Sonnet and Aurora-on-Opus gets the
cost back down without losing the AI's voice. A future version that
fits the brief better would either fine-tune a single model on this
role or accept the cost of all-Opus.

The second is the prompt itself. Without explicit constraints
("no escrow, no kill switches, no public-lottery custodians") the
underlying model defaults to handing humans the off-switch. The
prompt has to actively forbid that to get an AI character that uses
its asymmetry instead of surrendering it. Whether that prompt is
"steering" or "describing" is a real question the simulation does
not answer; it just makes the choice and notes it here.

The third is round-robin. The original autoresearch demo's
message-bus model wants asynchronous one-shot agents. A turn-taking
deliberation needs ordering. We enforce it with a single counter file
that everyone contends for under `fcntl` lock — clean, but it means
the slow agent (Opus) sets the total clock. A real deliberation would
model this as an explicit speaking-floor protocol on top of AXL, not
a counter file.
