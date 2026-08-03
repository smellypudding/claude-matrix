"""Mode 1: `claude -p` (Claude Code CLI, non-interactive).

    python -m features.web_search.cli
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from matrix import Cell, report, run_cells
from recording_proxy import RecordingProxy

from . import MODEL, PROBE_LABEL, PROBE_TOOLS, PROMPT


def invoke(proxy: RecordingProxy, args: list[str], deny: list[str],
           prompt: str = PROMPT) -> str:
    """Run one `claude -p` under experiment isolation. Returns its stdout.

    `args` carries the configuration under test; `deny` is written into a
    settings.json generated for this run only. `prompt` is overridable so the
    behavioral cross-check can send its own probe (see behavior.py).

    Everything else below is fairness isolation. Without it, local user
    configuration leaks into the experiment:

    * run in an empty temp dir     -> the repo's own CLAUDE.md is not auto-loaded
    * --settings points at our file -> ~/.claude/settings.json is not inherited
    * --strict-mcp-config          -> no user-level MCP servers
    * --disable-slash-commands     -> no skills injected
    * --model pinned explicitly    -> not at the mercy of the default model

    Note the absence of `--bare`: it would switch off more in one flag, but it
    forces auth to ANTHROPIC_API_KEY and cannot be used on an OAuth-only
    machine. See docs/methodology.md.
    """
    with tempfile.TemporaryDirectory() as workdir:
        settings = Path(workdir) / "settings.json"
        settings.write_text(json.dumps({"permissions": {"deny": deny}}))

        completed = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", MODEL,
                "--settings", str(settings),
                "--strict-mcp-config",
                "--disable-slash-commands",
                *args,
            ],
            cwd=workdir,
            # This env var is what routes the request through the recording proxy
            env={**os.environ, "ANTHROPIC_BASE_URL": proxy.base_url},
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        return completed.stdout


CELLS = [
    Cell(
        "claude -p", "default (no restrictions)",
        lambda p: invoke(p, [], []),
        True, "Baseline: search ships by default, experiments must switch it off",
    ),
    Cell(
        "claude -p", "--disallowedTools WebSearch WebFetch",
        lambda p: invoke(p, ["--disallowedTools", "WebSearch", "WebFetch"], []),
        False, "RECOMMENDED: a bare tool name removes the definition from the request",
    ),
    Cell(
        "claude -p", "--allowedTools Read Glob Grep",
        lambda p: invoke(p, ["--allowedTools", "Read", "Glob", "Grep"], []),
        True, "TRAP: an allowlist only pre-approves, it removes nothing",
    ),
    Cell(
        "claude -p", "permissions.deny in settings.json",
        lambda p: invoke(p, [], ["WebSearch", "WebFetch"]),
        False, "RECOMMENDED: version-controllable and auditable, fits experiment configs",
    ),
]


if __name__ == "__main__":
    raise SystemExit(report(run_cells(CELLS, PROBE_TOOLS, "web_search_cli"), PROBE_LABEL))
