# claude-matrix

Verifying how the same Claude feature actually behaves across **three invocation
modes**, with reproducible evidence.

| Invocation mode | What it is |
|---|---|
| `claude -p` | Claude Code CLI, non-interactive |
| Claude Agent SDK | `claude_agent_sdk.query()`, spawns the CLI as a subprocess |
| Anthropic direct API | `anthropic.Anthropic().messages.create()` |

This started from an evaluation-fairness problem: if a capability like web search
quietly stays live during an experiment, results become incomparable and
irreproducible. And whether a given switch really turns it off cannot be settled
by reading docs or watching model output — you have to look at the **real request
body** sent to Anthropic.

## Summary of findings

### [web search](docs/web_search.md)

| Invocation mode | How to disable |
|---|---|
| `claude -p` | `--disallowedTools WebSearch WebFetch`, or `permissions.deny` in `settings.json` |
| Agent SDK | `disallowed_tools=["WebSearch", "WebFetch"]` |
| direct API | Nothing to do — just don't declare it in `tools` |

* **`allowedTools` is not an allowlist.** It only pre-approves; it removes
  nothing. With `--allowedTools Read Glob Grep`, `WebSearch` is still shipped to
  the model in full. Removing a tool requires a **bare tool name on the deny
  side**.
* **The CLI's `WebSearch` is not the server-side `web_search_20260209`.** It is
  an ordinary custom tool (has `name`, no `type`). Probing by `type` prefix
  silently misses it under the CLI and Agent SDK.
* Risk ordering is the opposite of intuition: the direct API is structurally
  safe, while the two harness modes are the ones enabled by default.
* Behaviorally, default `claude -p` never actually reaches the network: the
  model calls the tool on every run and the permission system refuses it, since
  non-interactive mode has nobody to approve the prompt. That safety is
  **incidental** — one `--allowedTools WebSearch` away from being live, so
  disable the tools explicitly rather than relying on it.

Full conditions, raw evidence, and reasoning: [docs/web_search.md](docs/web_search.md).

## Method

[`recording_proxy.py`](recording_proxy.py) runs a local **reverse proxy**.
`ANTHROPIC_BASE_URL` points all three modes at it, every request body is written
to disk, and the tool list is asserted on directly.

Reverse proxy, not MITM: the client speaks plain HTTP to `127.0.0.1` and the
proxy speaks HTTPS upstream. So **no CA certificate to install**, and no API key
required — the claude.ai login that `claude` already has works as-is. Standard
library only. See [docs/methodology.md](docs/methodology.md).

## Running

```bash
python -m features.web_search.run         # all three modes, one summary table
python -m features.web_search.cli         # claude -p only
python -m features.web_search.agent_sdk   # Agent SDK only
python -m features.web_search.direct_api  # direct API only
```

The behavioral cross-check is separate because it costs far more — it performs
real agentic runs with live network access, 3 repeats per scenario:

```bash
python -m features.web_search.behavior    # 6 scenarios x 3 repeats
python -m features.web_search.behavior 1  # smoke test, 1 repeat each
```

The Agent SDK and direct API modes need extra dependencies. When they are
missing, those cells are **skipped explicitly** rather than passing silently:

```bash
python3 -m venv .venv && .venv/bin/pip install anthropic claude-agent-sdk
export ANTHROPIC_API_KEY=...    # only the two direct-API cells need this
```

## Layout

```
recording_proxy.py            # shared: recording reverse proxy
matrix.py                     # shared: matrix runner and table output
features/<feature>/
    __init__.py               # the question, plus constants shared across modes
    cli.py                    # mode 1: claude -p, runnable on its own
    agent_sdk.py              # mode 2: Agent SDK, runnable on its own
    direct_api.py             # mode 3: direct API, runnable on its own
    run.py                    # entry point: all modes, one table
    behavior.py               # behavioral cross-check (optional, costly)
docs/<feature>.md             # full experimental record for that feature
docs/methodology.md           # method, fairness isolation checklist, known limits
artifacts/                    # captured request bodies (not committed, see .gitignore)
```

## Adding a feature

Copy `features/web_search/` and change four things: the probe tool names in
`__init__.py`, the `CELLS` in each mode file, the per-cell expectations, and
`docs/<feature>.md`.

Each mode file holds only "how this mode issues a call" and "which configurations
we test". The shared logic is just `recording_proxy.py` and `matrix.py` —
deliberately no further abstraction, because the code is the documentation.
