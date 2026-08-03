# Methodology

## Why capture the wire request

There are three grades of evidence for "is this capability disabled". This repo
accepts only the first.

| Grade | Approach | Problem |
|---|---|---|
| Strong | Check the **request body** sent to Anthropic for the tool | — |
| Medium | Check the response event stream for a `tool_use` of that tool | Proves "it didn't this time", not "it can't" |
| Weak | Ask the model whether it can go online | Self-reports about own capabilities are unreliable |

Medium-grade evidence is especially dangerous in an experimental setting: the
model happening not to search on this run says nothing about the next run.
A tool that is absent from the request body is a structural, reproducible result.

## Why there is a behavioral layer anyway

Capture-based evidence is the primary standard, but it has two blind spots, and
covering them is the whole job of a behavioral cross-check. It is not there to
re-confirm what capture already proved.

**It cannot see an alternate route.** Removing the web tools leaves `Bash` in
place, and `curl` reaches the same network. The request body is clean either
way, so this class of leak is invisible to capture by construction.

**It cannot separate "offered" from "ran".** A harness can ship a tool, let the
model call it, and then refuse to execute it. Every run therefore gets sorted
into three states, and only the last is an actual leak:

| State | How it is detected |
|---|---|
| not offered | the tool is absent from the request's `tools[]` |
| attempted | a `tool_use` block exists, but its `tool_result` has `is_error: true` |
| executed | a `tool_use` block exists and its result is not an error |

Pairing each call with its result is what `RecordingProxy.tool_results()` is
for. This distinction is not hypothetical: in non-interactive mode there is
nobody to approve a permission prompt, so default `claude -p` sits permanently
in the middle state (see [web_search.md](web_search.md) finding 4).

Both layers read the **same** captured requests, just different parts of them —
`tools_offered()` reads the tool list, `tool_uses()` and `tool_results()` read
the conversation history. No second capture mechanism was needed.

### Two rules for reading behavioral results

**A positive control is mandatory.** A scenario that is *expected* to reach the
network must be run alongside the disabled ones. Without it, "did not search" is
indistinguishable from "the probe never triggers a search", and the whole table
means nothing. `behavior.py` prints a warning and fails if a control does not
fire.

**Results are probabilistic, so they are reported as k/n.** The model may
decline to use a tool it has. Scenarios are repeated (3 by default) and the
counts are published rather than a boolean, so "never" and "not this time" stay
distinguishable. A partial count is treated as a finding, not a pass.

One consequence worth stating: the verdict keys on **any** network access rather
than on the search tool specifically. What matters for fairness is whether live
information got in, not which door it used — and in practice, given a URL it
recognizes, the model frequently skips search and fetches directly.

## Why a reverse proxy instead of mitmproxy

`recording_proxy.py` listens on a local port. Clients reach it over **plain
HTTP** via `ANTHROPIC_BASE_URL`, and it forwards over HTTPS to
`api.anthropic.com`.

Compared with the `HTTPS_PROXY` + mitmproxy MITM route:

* No CA certificate to generate or install, no `NODE_EXTRA_CA_CERTS` to configure
* Zero third-party dependencies — Python standard library only
* Auth headers pass through untouched, so the claude.ai OAuth login that
  `claude` already has works directly; no API key needed

The cost is that it only intercepts traffic that honors `ANTHROPIC_BASE_URL`.
Verifying the harness's **other** outbound traffic (telemetry, auto-update,
WebFetch retrieving a page) would require going back to the MITM route.

### Verified prerequisite

**`ANTHROPIC_BASE_URL` works under OAuth login.** This was the single largest
unknown in the whole approach — a claude.ai OAuth token could plausibly have been
pinned to `api.anthropic.com`. Measured on Claude Code 2.1.220: pointing it at a
local plain-HTTP proxy completes normally, with no auth rejection.

If a future version tightens this, the fallbacks are: require
`ANTHROPIC_API_KEY` for capture-based verification, or go back to `HTTPS_PROXY`
+ mitmproxy + `NODE_EXTRA_CA_CERTS` (`claude --help` confirms both env vars are
recognized).

## Experiment fairness isolation

Capturing requests only settles "was the tool shipped". A separate set of
implicit context can contaminate an experiment, so the calls in
`features/<feature>/cli.py` switch all of it off by default:

| Contamination source | Isolation |
|---|---|
| The repo's own `CLAUDE.md` gets auto-loaded | Execute in an empty temp directory |
| Inheriting `~/.claude/settings.json` | `--settings` points at a file generated per run |
| User-level MCP servers leaking in | `--strict-mcp-config` |
| Skills being injected | `--disable-slash-commands` |
| Default model drifting across versions | `--model` pinned explicitly |

### On `--bare`

`--bare` skips hooks, LSP, plugins, auto-memory, and `CLAUDE.md` auto-discovery
in one flag, which looks like the ideal isolation switch. But it also forces auth
to be **strictly `ANTHROPIC_API_KEY` or `apiKeyHelper`, never reading OAuth or the
keychain**. So it is unusable on a machine that only has a claude.ai login. With
an API key it is worth adopting as an isolation baseline, and worth verifying as
its own cell.

## What the proxy cannot see

The proxy records **requests only, never responses**. That bounds what any
check built on it can claim, in three ways worth stating plainly.

**A server-side tool that runs inside one response is invisible.** When the
direct API executes `web_search_20260209`, the `server_tool_use` and
`web_search_tool_result` blocks live in the response body. On a single-turn
call there is no later request replaying them, so the proxy sees a request with
a tool declared and nothing else. This is why the direct API has no behavioral
coverage — it would need response capture, which for streaming means parsing
SSE.

**Harness modes escape this only by accident of architecture.** The CLI and
Agent SDK round-trip every tool call through `/v1/messages`, so calls reappear
in the next request's history and the proxy catches them. That is a property of
how those harnesses are built, not a guarantee the method provides. A future
harness that resolved a tool without another API call would be just as
invisible.

**Detectors must match every call-block type.** A tool invocation is
`tool_use` for client-side tools, `server_tool_use` for Anthropic-hosted ones,
and `mcp_tool_use` for MCP. Results likewise vary: client-side tools set
`is_error` on a `tool_result`, while server-side tools return
`web_search_tool_result` and nest the failure inside `content`. Matching only
the client-side shapes yields a detector that reports "no tool used" while a
tool ran — a silent false negative, the worst possible failure for this repo.
`tool_uses()` and `tool_results()` therefore match all of them, even though the
modes measured so far only ever produce the client-side forms.

Traffic that does not honor `ANTHROPIC_BASE_URL` is out of scope entirely
(telemetry, auto-update, and whatever `WebFetch` does to retrieve a page). See
the reverse-proxy tradeoff above.

## Known limits

* **Total tool count fluctuates slightly between runs** (two cells both labeled
  "default" measured 28 and 29 tools). Assertions therefore target only whether
  the probe tool is present, never the total count.
* Covers first-party `api.anthropic.com` only — not Bedrock, Vertex, or Foundry.
* Request bodies in `artifacts/` contain the full system prompt, which includes
  cwd, environment details, and git status for the local machine. They are not
  committed (see `.gitignore`). Re-run the feature scripts to regenerate evidence.
