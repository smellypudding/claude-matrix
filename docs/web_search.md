# web search: how to actually disable it in each invocation mode

Reproduce: `python -m features.web_search.run` &nbsp;|&nbsp; Code: [`features/web_search/`](../features/web_search/)

## The problem

For evaluation experiments, web search is a fairness hazard: the model may pick
up information it should not have, making results incomparable and
irreproducible. We need to disable it in all three invocation modes, and be able
to show evidence.

The criterion is **whether the tool appears in the real request body sent to
Anthropic** — not "the model says it didn't search", and not "it didn't search on
this run". Rationale in [methodology.md](methodology.md).

## Conditions

| Item | Value |
|---|---|
| Date | 2026-07-30 |
| Claude Code | 2.1.220 |
| Model | `claude-opus-5` (pinned explicitly) |
| anthropic SDK | 0.120.2 |
| Auth | claude.ai OAuth (no `ANTHROPIC_API_KEY`) |
| Capture | `ANTHROPIC_BASE_URL` pointed at a local recording reverse proxy |

CLI and Agent SDK calls both run under fairness isolation (empty temp dir, no
inherited user settings, `--strict-mcp-config`, `--disable-slash-commands`) —
checklist in methodology.md.

## Results

| # | Invocation mode | Configuration | Search tool | Verdict |
|---|---|---|---|---|
| 1 | `claude -p` | default | **present** | baseline |
| 2 | `claude -p` | `--disallowedTools WebSearch WebFetch` | absent | recommended |
| 3 | `claude -p` | `--allowedTools Read Glob Grep` | **present** | trap |
| 4 | `claude -p` | `permissions.deny` in `settings.json` | absent | recommended |
| 5 | Agent SDK | default | **present** | baseline |
| 6 | Agent SDK | `disallowed_tools=["WebSearch","WebFetch"]` | absent | recommended |
| 7 | direct API | no `tools` declared | absent | structurally safe |
| 8 | direct API | `web_search_20260209` declared | **present** | control |

Rows 7 and 8 require `ANTHROPIC_API_KEY`. This machine has only a claude.ai
subscription login, so those two cells are skipped explicitly (the script
deliberately does not read `~/.claude/.credentials.json`). The other six ran.

### Raw evidence

Captured `tools[]` lengths — disabling removes exactly 2 entries (`WebSearch`
plus `WebFetch`):

| Cell | Configuration | `tools[]` length | web tools present |
|---|---|---|---|
| 1 | default | 28 | `WebFetch`, `WebSearch` |
| 2 | `--disallowedTools` | 26 | none |
| 3 | `--allowedTools` | 30 | `WebFetch`, `WebSearch` |
| 4 | `permissions.deny` | 26 | none |
| 5 | Agent SDK default | 29 | `WebFetch`, `WebSearch` |
| 6 | Agent SDK `disallowed_tools` | 27 | none |

Total tool count fluctuates between runs (28 / 29 / 30), so assertions target
only whether the probe tool is present, never the total.

## Three findings

### 1. `allowedTools` is not an allowlist

Cell 3 is the most valuable result here: with `--allowedTools Read Glob Grep`,
`WebSearch` and `WebFetch` are still **shipped to the model in full** (30 tools,
more than the baseline).

Allow rules only pre-approve. They decide whether a tool call needs a
confirmation prompt, not whether the tool exists. Unlisted tools are still sent
and simply fall through to the permission mode for adjudication.

To **remove a tool from the request**, use a **bare tool name** on the deny side:
`--disallowedTools WebSearch`, or `permissions.deny: ["WebSearch"]` in
settings.json. Scoped forms such as `Bash(rm *)` only block matching calls; the
tool itself stays in the request.

By the same logic, a `PreToolUse` hook denial is a weak guarantee: the tool
definition remains, only the call is refused. For experiments, prefer mechanisms
that genuinely remove the tool definition.

### 2. The CLI's search tool is not the server-side tool

The official tools-reference says "WebSearch runs a query against Anthropic's web
search backend", which invites the assumption that `claude -p` ships the
server-side `web_search_20260209`. The capture says otherwise:

```jsonc
// captured from claude -p — an ordinary custom tool, no type field
{ "name": "WebSearch", "input_schema": { "properties": { "query": {...},
    "allowed_domains": {...}, "blocked_domains": {...} } } }

// declaring the server-side tool on the direct API looks like this instead
{ "type": "web_search_20260209", "name": "web_search" }
```

The CLI ships it as a client-side tool, performs the search itself, and feeds the
results back as an ordinary `tool_result`.

**Consequence: probing for a search tool by `type` prefix silently misses it
under the CLI and Agent SDK.** Detection must match both `name` and `type` —
which is what `RecordingProxy.tool_calls_for` does.

Note also that `WebFetch` is a separate network path (the harness retrieves the
page and summarizes it with a small model), so it must be disabled alongside
`WebSearch`.

### 3. Risk ordering is the opposite of intuition

The direct API is the **safest** of the three: a server-side tool exists only if
explicitly written into `tools[]`, so the risk comes solely from your own code.

The two harness modes carry the most risk, because they ship enabled by default.
An experiment script that calls `claude -p` with no restrictions has search
capability present by default.

## Recommendations

```bash
# claude -p
claude -p "..." --disallowedTools WebSearch WebFetch
```

```jsonc
// or in the experiment's settings.json — version-controllable and auditable
{ "permissions": { "deny": ["WebSearch", "WebFetch"] } }
```

```python
# Agent SDK
ClaudeAgentOptions(disallowed_tools=["WebSearch", "WebFetch"])

# direct API: just omit web_search_* from tools; no switch needed
```

## Open items

* Cells 7 and 8 need an `ANTHROPIC_API_KEY` to actually run
* `--bare` deserves its own cell as an isolation baseline, but it forces an API
  key (see methodology.md)
* Behavioral cross-check not yet added: run a prompt that cannot be answered
  without going online and inspect the event stream for a `WebSearch` call
