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

## Known limits

* **Total tool count fluctuates slightly between runs** (two cells both labeled
  "default" measured 28 and 29 tools). Assertions therefore target only whether
  the probe tool is present, never the total count.
* Covers first-party `api.anthropic.com` only — not Bedrock, Vertex, or Foundry.
* Request bodies in `artifacts/` contain the full system prompt, which includes
  cwd, environment details, and git status for the local machine. They are not
  committed (see `.gitignore`). Re-run the feature scripts to regenerate evidence.
