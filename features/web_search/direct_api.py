"""Mode 3: Anthropic direct API (`anthropic.Anthropic().messages.create`).

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python -m features.web_search.direct_api

This mode is structurally safe: a server-side tool exists only if it is
declared in tools[], so not declaring it is enough. The risk comes from your
own code, never from a harness default. The two cells below verify that in
both directions.
"""

from __future__ import annotations

import os

from matrix import Cell, Skip, report, run_cells
from recording_proxy import RecordingProxy

from . import MODEL, PROBE_LABEL, PROBE_TOOLS, PROMPT


def invoke(proxy: RecordingProxy, tools: list[dict]) -> None:
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as exc:
        raise Skip("pip install anthropic") from exc

    # Deliberately not reading ~/.claude/.credentials.json: that is a claude.ai
    # subscription login, not something to drive the API SDK with. Bring your
    # own API key to run these two cells.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise Skip("ANTHROPIC_API_KEY required")

    # This SDK takes base_url directly, no env var juggling like the Agent SDK
    client = anthropic.Anthropic(base_url=proxy.base_url)
    client.messages.create(
        model=MODEL,
        max_tokens=64,
        tools=tools,  # type: ignore[arg-type]
        messages=[{"role": "user", "content": PROMPT}],
    )


CELLS = [
    Cell(
        "direct API", "no tools declared",
        lambda p: invoke(p, []),
        False, "Structurally safe: absent unless declared, no switch needed",
    ),
    Cell(
        "direct API", "web_search_20260209 declared",
        lambda p: invoke(p, [{"type": "web_search_20260209", "name": "web_search"}]),
        True, "Control: present only because we put it there ourselves",
    ),
]


if __name__ == "__main__":
    raise SystemExit(report(run_cells(CELLS, PROBE_TOOLS, "web_search_direct_api"), PROBE_LABEL))
