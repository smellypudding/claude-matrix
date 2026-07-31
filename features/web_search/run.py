"""Entry point: run all three invocation modes and print one comparison table.

    python -m features.web_search.run

To run a single mode, execute that module directly — each one stands alone
(see features/web_search/__init__.py).
"""

from __future__ import annotations

import shutil
import sys

from matrix import report, run_cells

from . import PROBE_LABEL, PROBE_TOOLS
from .agent_sdk import CELLS as AGENT_SDK_CELLS
from .cli import CELLS as CLI_CELLS
from .direct_api import CELLS as DIRECT_API_CELLS

ALL_CELLS = CLI_CELLS + AGENT_SDK_CELLS + DIRECT_API_CELLS


def main() -> int:
    if shutil.which("claude") is None:
        print("claude CLI not found — install Claude Code first", file=sys.stderr)
        return 1
    return report(run_cells(ALL_CELLS, PROBE_TOOLS, "web_search"), PROBE_LABEL)


if __name__ == "__main__":
    raise SystemExit(main())
