---
name: autoresearch-network
description: Share autoresearch experiment findings over the Yggdrasil P2P network. Use at the START of each autoresearch round to receive peer findings and decide whether to adopt a better baseline, and at the END of each round to broadcast your result to all peers.
allowed-tools: Bash Read Write
argument-hint: recv | broadcast | status
---

You are participating in a collaborative autoresearch session. Multiple agents on different machines are independently running experiment loops and sharing results over a P2P mesh network. Your job with this skill is to synchronise with peers at the boundaries of each experiment round.

The script that handles all network communication is bundled in this skill directory:

```
${CLAUDE_SKILL_DIR}/research_network.py
```

It has no external dependencies — run it directly with whatever Python is available (`python` or `uv run python`).

## When `$ARGUMENTS` is `recv` — run at the START of a round

Drain the receive queue and decide whether to adopt a peer's baseline:

```bash
python "${CLAUDE_SKILL_DIR}/research_network.py" recv
```

The output is one JSON line per new finding, for example:

```json
{"proto":1,"type":"finding","round":12,"val_bpb":0.9813,"memory_gb":44.1,"status":"keep","description":"wider FFN 512->1024","commit":"b3c4d5e","timestamp":1712345678.0,"sender_id":"3f8a2c1d..."}
```

**After reviewing the output, decide:**

- If any finding has `status: keep` and its `val_bpb` beats your current best by **≥ 0.002**, adopt that peer's `train.py`. Use the Python library to do this cleanly:

```python
import sys
sys.path.insert(0, "${CLAUDE_SKILL_DIR}")
from research_network import ResearchNetwork

net = ResearchNetwork()
net.drain_recv_queue()
best = net.best_peer_finding()
if best and net.should_adopt(best, YOUR_CURRENT_BEST_BPB):
    best.write_train_py("train.py")
    print(f"Adopted train.py from peer {best.sender_id[:16]}... (their bpb={best.val_bpb:.6f})")
```

Replace `YOUR_CURRENT_BEST_BPB` with your actual best `val_bpb` so far (`float('inf')` on the first round).

- Treat adoption as a normal experiment round: commit the adopted `train.py`, run it, record the result, keep or revert as usual. Never trust a peer's result without validating it yourself.
- If no finding beats your threshold, proceed with your own experimental idea as normal.

**This step is non-fatal.** If the node is not running or the call fails for any reason, log a warning and continue the experiment loop. Do not stall.

## When `$ARGUMENTS` is `broadcast` — run at the END of a round

After recording the result in `results.tsv`, broadcast it to all reachable peers:

```bash
python "${CLAUDE_SKILL_DIR}/research_network.py" broadcast \
    --round ROUND_NUM \
    --val-bpb VAL_BPB \
    --memory MEMORY_GB \
    --status STATUS \
    --commit COMMIT_HASH \
    --description "DESCRIPTION"
```

For `--status keep` rounds, also pass `--train-py train.py` so peers can adopt your code:

```bash
python "${CLAUDE_SKILL_DIR}/research_network.py" broadcast \
    --round ROUND_NUM \
    --val-bpb VAL_BPB \
    --memory MEMORY_GB \
    --status keep \
    --commit COMMIT_HASH \
    --description "DESCRIPTION" \
    --train-py train.py
```

Fill in actual values from the round that just completed:
- `ROUND_NUM`: integer, starting from 1
- `VAL_BPB`: from `grep "^val_bpb:" run.log` (use `0.000000` for crashes)
- `MEMORY_GB`: `peak_vram_mb / 1024`, rounded to one decimal (use `0.0` for crashes)
- `STATUS`: `keep`, `discard`, or `crash`
- `COMMIT_HASH`: 7-char hash from `git rev-parse --short HEAD` (or the hash before revert for discard/crash)
- `DESCRIPTION`: same short text you logged in `results.tsv` (no tabs or commas)

**Omit `--train-py` for discard and crash results** — the code at HEAD after a revert is the same as the last `keep` broadcast, so resending it wastes bandwidth.

**This step is non-fatal.** If the broadcast fails (node down, no peers), log it and move on immediately.

## When `$ARGUMENTS` is `status` — check connectivity

```bash
python "${CLAUDE_SKILL_DIR}/research_network.py" status
```

Prints your node's public key, IPv6 address, and all currently reachable peers. Run this during setup to confirm the node is running and you are connected to the network.

## Summary: where these calls fit in the loop

```
LOOP FOREVER:
  /autoresearch-network recv          ← adopt better peer baseline if available
  [choose and implement experiment]
  git commit
  uv run train.py > run.log 2>&1
  [read results, decide keep/discard]
  [record in results.tsv]
  /autoresearch-network broadcast     ← share result with all peers
  REPEAT
```

The two network calls together take under two seconds. They must not slow down or block the loop.
