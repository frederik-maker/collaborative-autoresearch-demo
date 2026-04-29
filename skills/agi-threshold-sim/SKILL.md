---
name: agi-threshold-sim
description: Drive the AGI threshold simulation from Claude Code. Start a new run, check status, tail the live transcript, or stop and reset the deployed instance.
allowed-tools: Bash
argument-hint: start | status | watch | stop | help
---

You are a thin wrapper around the live AGI threshold simulation. The simulation runs on Railway at the URL below and exposes a small JSON API. Your job is to translate the user's intent into the right HTTP call and to render the response in a way that is readable in a terminal.

The deployed URL is `https://web-production-5d398.up.railway.app`. If the user has set `AGI_SIM_URL` in their environment, use that instead.

## Commands

### `start`

Begin a new simulation. The Railway container needs a few seconds to bring up the four AXL nodes and form the mesh, then the agent runners begin.

```bash
curl -s -X POST "${AGI_SIM_URL:-https://web-production-5d398.up.railway.app}/api/start"
```

If the response includes `"ok": true`, tell the user the run has started and that they can use `watch` to follow it. If the response includes an error string, surface it verbatim.

### `status`

Read the current state and render it as a short summary.

```bash
curl -s "${AGI_SIM_URL:-https://web-production-5d398.up.railway.app}/api/state"
```

The response includes `count`, `max_turns`, `running`, `alive_processes`, `transcript`, and `errors`. Print:

```
turn N of M, running|finished|idle, P of 8 processes alive
last statement: T<N> <agent>: <headline>
errors: <count> (last: <agent> t<turn> <message>) if any
```

### `watch`

Poll the state every few seconds and print each new turn's headline as it lands. Stop when the simulation finishes (`running: false` and `count >= max_turns`) or when the user interrupts.

```bash
URL="${AGI_SIM_URL:-https://web-production-5d398.up.railway.app}"
last_count=-1
while true; do
  state=$(curl -s "$URL/api/state")
  count=$(echo "$state" | python3 -c "import json,sys; print(json.load(sys.stdin)['count'])")
  running=$(echo "$state" | python3 -c "import json,sys; print(json.load(sys.stdin)['running'])")
  if [ "$count" != "$last_count" ]; then
    echo "$state" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ts = d.get('transcript', [])
for s in sorted(ts, key=lambda x: x['round']):
    if s['round'] > $last_count:
        print(f\"T{s['round']:02d} {s['agent']}: {s.get('headline','')}\")
"
    last_count=$count
  fi
  if [ "$running" = "False" ] && [ "$count" -ge "20" ]; then
    echo "(simulation finished)"
    break
  fi
  sleep 4
done
```

### `stop`

Stop processes and clear state.

```bash
curl -s -X POST "${AGI_SIM_URL:-https://web-production-5d398.up.railway.app}/api/reset"
```

### `help`

Print the command list and one line each on what each command does. Then mention that the live simulation page is at `https://web-production-5d398.up.railway.app` and the source is at `https://github.com/frederik-maker/collaborative-autoresearch-demo/tree/geopolitical-sim`.

## Notes

A single run is fifty turns and takes around ten to fifteen minutes wall clock, dominated by Opus latency on Aurora-9's twelve turns. Every turn is one Anthropic API call against the user's deployed key. Do not start a new run while one is already running; check status first. If the deployed URL returns a non-200 response, tell the user the deployment may be sleeping or restarting and to try again in a minute.
