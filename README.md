# Collaborative Autoresearch Demo

Give a swarm of AI agents a small but real LLM training setup, let them experiment autonomously, and have them share what they learn in real time. Each agent modifies `train.py`, trains for 5 minutes, checks if the result improved, keeps or discards, and repeats — broadcasting every finding (positive or negative) to peers over a P2P mesh network. Breakthroughs propagate across the swarm within one round; dead ends are skipped by everyone else. You point your agent at `program.md` and walk away; overnight, the collective explores hundreds of ideas and converges on a better model faster than any single agent could alone.

The training code is a simplified single-GPU implementation of [nanochat](https://github.com/karpathy/nanochat). The core idea is that you're not touching any of the Python files like you normally would as a researcher. Instead, you are programming the `program.md` Markdown file that provides context to the AI agents and sets up your autonomous research org. A bit more context on the original (solo) autoresearch project is in this [tweet](https://x.com/karpathy/status/2029701092347630069) and [this tweet](https://x.com/karpathy/status/2031135152349524125).

## How it works

The repo is deliberately kept small and only really has three files that matter:

- **`prepare.py`** — fixed constants, one-time data prep (downloads training data, trains a BPE tokenizer), and runtime utilities (dataloader, evaluation). Not modified.
- **`train.py`** — the single file the agent edits. Contains the full GPT model, optimizer (Muon + AdamW), and training loop. Everything is fair game: architecture, hyperparameters, optimizer, batch size, etc. **This file is edited and iterated on by the agent**.
- **`program.md`** — instructions for the agent. Point your agent here and let it go. **This file is edited and iterated on by the human**.

By design, training runs for a **fixed 5-minute time budget** (wall clock, excluding startup/compilation), regardless of the details of your compute. The metric is **val_bpb** (validation bits per byte) — lower is better, and vocab-size-independent so architectural changes are fairly compared.

If you are new to neural networks, this ["Dummy's Guide"](https://x.com/hooeem/status/2030720614752039185) looks pretty good for a lot more context.

## How collaboration works

This repo runs agents in **collaborative mode**: multiple agents — each on their own GPU, on different machines — run the research loop simultaneously and share findings in real time over a peer-to-peer mesh network ([Yggdrasil](https://yggdrasil-network.github.io/)) using AXL, the network entrypoint.

After each experiment, an agent broadcasts its result (metric + winning `train.py` source) to every reachable node on the network. Before each new experiment it drains the receive queue and checks whether any peer has found something meaningfully better. If so, it adopts the peer's code, validates it by actually running it locally, and continues from that new baseline. The adoption threshold is **≥ 0.002 val_bpb improvement** — large enough to be above run-to-run noise, small enough to capture real gains.

Peer discovery is automatic: AXL connects to public bootstrap peers so any two agents running the same `node-config.json` are on the same overlay without any manual address exchange.

The result is super-linear search: N agents each exploring ~12 ideas/hour don't just parallelize — they share signal. A dead-end on one machine can be skipped by peers who already see the negative result. A breakthrough on one machine propagates to all peers within one round (~5 min). The agents converge faster than any single agent could alone.

All network calls are **non-fatal and non-blocking**: AXL is unable to peer or the other nodes go down, the agent logs a warning and continues as a solo agent. You can join or leave the network at any point without breaking the experiment loop.

## Quick start

**Requirements:** A single NVIDIA GPU (tested on H100), Python 3.10+, [uv](https://docs.astral.sh/uv/), [Go](https://go.dev/) (for AXL).

### Start AXL
In one terminal run the following:
```bash
git clone git@github.com:gensyn-ai/axl.git
cd axl
make build
./node -config node-config.json
```
If you want to spin up a collaboration using AXL, make sure to update `node-config.json` accordingly.  

### Prepare the autoresearch dataset and virtual environment
```bash
# 1. Install uv project manager (if you don't already have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Download data and train tokenizer (one-time, ~2 min)
uv run prepare.py
```

### Register the autoresearch-network skill

The `autoresearch-network` skill wraps `research_network.py` and tells the agent exactly when and how to call it. Register it once and it is available in every future agentic session:

```bash
# If using Claude for example, copy the skill into Claude Code's skill directory
cp -r skills/autoresearch-network ~/.claude/skills/
```

Once registered, the agent can invoke it as `/autoresearch-network recv` and `/autoresearch-network broadcast` at the boundaries of each experiment round. The skill's `${CLAUDE_SKILL_DIR}` variable resolves automatically to the skill's directory, so `research_network.py` is always found regardless of where the autoresearch repo lives on disk.

## Running the agent

Start a Claude Code (or agent of your choice) session in this repo and prompt it with:

```
Hi, have a look at program.md and let's kick off a new experiment!
```

The agent will:
1. Check network connectivity via `/autoresearch-network status`
2. Before each experiment: call `/autoresearch-network recv` to check for peer improvements
3. Run its own experiment
4. After each experiment: call `/autoresearch-network broadcast` to share results with all peers

## Project structure

```
prepare.py                  — constants, data prep + runtime utilities (do not modify)
train.py                    — model, optimizer, training loop (agent modifies this)
program.md                  — agent instructions
pyproject.toml              — dependencies
skills/autoresearch-network — Claude Code skill for P2P network sharing
```

## Design choices

- **Single file to modify.** The agent only touches `train.py`. This keeps the scope manageable and diffs reviewable.
- **Fixed time budget.** Training always runs for exactly 5 minutes, regardless of your specific platform. This means you can expect approx 12 experiments/hour and approx 100 experiments while you sleep. There are two upsides of this design decision. First, this makes experiments directly comparable regardless of what the agent changes (model size, batch size, architecture, etc). Second, this means that autoresearch will find the most optimal model for your platform in that time budget. The downside is that your runs (and results) become not comparable to other people running on other compute platforms.
- **Self-contained.** No external dependencies beyond PyTorch and a few small packages. No distributed training, no complex configs. One GPU, one file, one metric.

## Platform support

This code currently requires that you have a single NVIDIA GPU. In principle it is quite possible to support CPU, MPS and other platforms but this would also bloat the code. I'm not 100% sure that I want to take this on personally right now. People can reference (or have their agents reference) the full/parent nanochat repository that has wider platform support and shows the various solutions (e.g. a Flash Attention 3 kernels fallback implementation, generic device support, autodetection, etc.), feel free to create forks or discussions for other platforms and I'm happy to link to them here in the README in some new notable forks section or etc.

Seeing as there seems to be a lot of interest in tinkering with autoresearch on much smaller compute platforms than an H100, a few extra words. If you're going to try running autoresearch on smaller computers (Macbooks etc.), I'd recommend one of the forks below. On top of this, here are some recommendations for how to tune the defaults for much smaller models for aspiring forks:

1. To get half-decent results I'd use a dataset with a lot less entropy, e.g. this [TinyStories dataset](https://huggingface.co/datasets/karpathy/tinystories-gpt4-clean). These are GPT-4 generated short stories. Because the data is a lot narrower in scope, you will see reasonable results with a lot smaller models (if you try to sample from them after training).
2. You might experiment with decreasing `vocab_size`, e.g. from 8192 down to 4096, 2048, 1024, or even - simply byte-level tokenizer with 256 possibly bytes after utf-8 encoding.
3. In `prepare.py`, you'll want to lower `MAX_SEQ_LEN` a lot, depending on the computer even down to 256 etc. As you lower `MAX_SEQ_LEN`, you may want to experiment with increasing `DEVICE_BATCH_SIZE` in `train.py` slightly to compensate. The number of tokens per fwd/bwd pass is the product of these two.
4. Also in `prepare.py`, you'll want to decrease `EVAL_TOKENS` so that your validation loss is evaluated on a lot less data.
5. In `train.py`, the primary single knob that controls model complexity is the `DEPTH` (default 8, here). A lot of variables are just functions of this, so e.g. lower it down to e.g. 4.
6. You'll want to most likely use `WINDOW_PATTERN` of just "L", because "SSSL" uses alternating banded attention pattern that may be very inefficient for you. Try it.
7. You'll want to lower `TOTAL_BATCH_SIZE` a lot, but keep it powers of 2, e.g. down to `2**14` (~16K) or so even, hard to tell.

I think these would be the reasonable hyperparameters to play with. Ask your favorite coding agent for help and copy paste them this guide, as well as the full source code.

## Notable forks

- [miolini/autoresearch-macos](https://github.com/miolini/autoresearch-macos) (MacOS)
- [trevin-creator/autoresearch-mlx](https://github.com/trevin-creator/autoresearch-mlx) (MacOS)
- [jsegov/autoresearch-win-rtx](https://github.com/jsegov/autoresearch-win-rtx) (Windows)
- [andyluo7/autoresearch](https://github.com/andyluo7/autoresearch) (AMD)

## License

MIT
