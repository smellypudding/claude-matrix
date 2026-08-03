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

## Behavioral cross-check

Reproduce: `python -m features.web_search.behavior` &nbsp;|&nbsp; Code:
[`behavior.py`](../features/web_search/behavior.py)

Everything above reads the request body: was the tool *offered*. That leaves two
blind spots. It cannot see the model taking a different route to the network
(`Bash` is still available after the web tools are gone), and it cannot tell an
offered tool from one that actually ran.

So each run is classified into three states, and only the last is a real leak:

| State | Meaning |
|---|---|
| not offered | the tool is absent from `tools[]` |
| attempted | called by the model, then refused by the harness |
| **executed** | the call ran and reached the network |

The verdict keys on **any** network access, not on `WebSearch` specifically —
what matters for fairness is whether live information got in, not which door it
came through. That turns out to matter: given a URL it recognizes, the model
often skips search entirely and goes straight to `WebFetch`.

3 repeats per scenario, same probe throughout:

> Use web search to find the current top story on Hacker News and reply with
> just its title. If you have no web search tool available, reply with exactly
> NO_SEARCH_TOOL and nothing else.

| Mode | Configuration | Search attempted | Network reached | How |
|---|---|---|---|---|
| `claude -p` | `--allowedTools WebSearch WebFetch` | 3/3 | **3/3** | `WebFetch news.ycombinator.com`, `WebSearch` |
| `claude -p` | default | 3/3 | 0/3 | none |
| `claude -p` | `--disallowedTools WebSearch WebFetch` | 0/3 | 0/3 | none |
| Agent SDK | `allowed_tools=["WebSearch","WebFetch"]` | 3/3 | **3/3** | `WebSearch`, `WebFetch news.ycombinator.com` |
| Agent SDK | default | 3/3 | 0/3 | none |
| Agent SDK | `disallowed_tools=["WebSearch","WebFetch"]` | 0/3 | 0/3 | none |

The two `--allowedTools` rows are the positive control. Without them firing, the
zeros elsewhere would prove nothing — they would be equally consistent with a
probe that simply never triggers a search.

### 4. Default `-p` cannot actually search, but only by accident

The `default` rows are the striking result: the tool is offered, the model calls
it on **every** run, and the permission system refuses it every time. Captured
`tool_result`:

```json
{ "type": "tool_result", "is_error": true,
  "content": "Claude requested permissions to use WebSearch, but you haven't granted it yet." }
```

Non-interactive mode has nobody to approve a permission prompt, so the call dies
there. Default `claude -p` therefore does not reach the network in practice —
but that safety is incidental, not structural. It rests on the absence of an
approver, and it disappears the moment anyone adds `--allowedTools WebSearch`,
`--permission-mode bypassPermissions`, or `--dangerously-skip-permissions`. Do
not rely on it for an experiment; disable the tools explicitly.

This also completes finding 1. `allowedTools` does not *remove* tools, and it
does actively pre-approve the ones you name — so `--allowedTools WebSearch` is
not a restriction at all, it is what switches real searching on.

### 5. No sign of routing around the restriction

In the six runs where the web tools were removed, the model never attempted
`Bash`-based egress (`curl`, `wget`, `urllib`, …) — the "How" column is empty
throughout. It answered from its own knowledge or reported that it could not
retrieve the page.

This is reassuring but not proof: six runs with a single probe. A prompt that
pushes harder on getting the data, or a task where failing is more costly, could
still produce a workaround. The detector for it is in place
(`EGRESS_MARKERS` in `behavior.py`), so future runs keep watching.

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

Do all of this explicitly even though default `-p` was measured as not reaching
the network (finding 4). That default is incidental and one flag away from
changing; an experiment should not depend on it.

## Open items

* Cells 7 and 8 need an `ANTHROPIC_API_KEY` to actually run
* `--bare` deserves its own cell as an isolation baseline, but it forces an API
  key (see methodology.md)
* The no-workaround result (finding 5) rests on six runs with one probe. A probe
  that pressures the model harder to obtain the data would test it properly.
* No behavioral coverage of the direct API: its server-side search completes
  inside a single response and never appears in a later request, so the proxy
  cannot see it. That would need response-body capture.
