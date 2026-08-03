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


def invoke(proxy: RecordingProxy, disallowed: list[str],
           prompt: str = PROMPT, allowed: list[str] | None = None) -> str:
    """Run one Agent SDK query. Returns the final result text.

    The Agent SDK spawns the CLI as a subprocess and that subprocess inherits
    the environment, so the same recording proxy works here with no
    mode-specific adaptation.

    `prompt` and `allowed` are overridable for the behavioral cross-check
    (behavior.py), which needs its own probe and needs to pre-approve the web
    tools to get them past the permission check.
    """
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query  # type: ignore[import-not-found]
    except ImportError as exc:
        raise Skip("pip install claude-agent-sdk") from exc

    final_text: list[str] = []

    async def go() -> None:
        options = ClaudeAgentOptions(model=MODEL, disallowed_tools=disallowed,
                                     allowed_tools=allowed or [])
        async for message in query(prompt=prompt, options=options):
            # ResultMessage closes out the run and carries the final answer
            if isinstance(message, ResultMessage) and message.result:
                final_text.append(message.result)

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

    return "\n".join(final_text)


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
