"""Mode 2: Claude Agent SDK (`claude_agent_sdk.query`).

    pip install claude-agent-sdk
    python -m features.web_search.agent_sdk
"""

from __future__ import annotations

import asyncio
import os

from matrix import Cell, Skip, report, run_cells
from recording_proxy import RecordingProxy

from . import MODEL, PROBE_LABEL, PROBE_TOOLS, PROMPT


def invoke(proxy: RecordingProxy, disallowed: list[str]) -> None:
    """Run one Agent SDK query.

    The Agent SDK spawns the CLI as a subprocess and that subprocess inherits
    the environment, so the same recording proxy works here with no
    mode-specific adaptation.
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query  # type: ignore[import-not-found]
    except ImportError as exc:
        raise Skip("pip install claude-agent-sdk") from exc

    async def go() -> None:
        options = ClaudeAgentOptions(model=MODEL, disallowed_tools=disallowed)
        async for _ in query(prompt=PROMPT, options=options):
            pass

    # The SDK exposes no base_url parameter, so the env var is the only lever.
    # Restore it afterwards so the change does not leak into later cells.
    previous = os.environ.get("ANTHROPIC_BASE_URL")
    os.environ["ANTHROPIC_BASE_URL"] = proxy.base_url
    try:
        asyncio.run(go())
    finally:
        if previous is None:
            os.environ.pop("ANTHROPIC_BASE_URL", None)
        else:
            os.environ["ANTHROPIC_BASE_URL"] = previous


CELLS = [
    Cell(
        "Agent SDK", "default (no restrictions)",
        lambda p: invoke(p, []),
        True, "Baseline: ships enabled by default, same as the CLI",
    ),
    Cell(
        "Agent SDK", 'disallowed_tools=["WebSearch","WebFetch"]',
        lambda p: invoke(p, ["WebSearch", "WebFetch"]),
        False, "RECOMMENDED: same mechanism and effect as the CLI's --disallowedTools",
    ),
]


if __name__ == "__main__":
    raise SystemExit(report(run_cells(CELLS, PROBE_TOOLS, "web_search_agent_sdk"), PROBE_LABEL))
