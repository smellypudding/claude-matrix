"""Behavioral cross-check: did the search actually reach the network, and if
it could not, did the model find another way there?

    python -m features.web_search.behavior      # 3 repeats per scenario
    python -m features.web_search.behavior 1    # smoke test, 1 repeat

Why this exists
---------------
Every other result in this feature comes from inspecting the request body: is
the search tool in `tools[]` or not. That is strong evidence, but it has two
blind spots this module covers.

**It cannot see an alternate route to the network.** Disabling `WebSearch` and
`WebFetch` leaves `Bash` in the tool list, and the model can reach for `curl`
from there. Capture-based checking will never report that — the request body
genuinely contains no search tool.

**It cannot tell "offered" from "actually ran".** A tool can be shipped to the
model, called by the model, and then refused by the harness. That is exactly
what happens in non-interactive mode: there is nobody to approve a permission
prompt, so the call comes back `is_error: true` and never reaches the network.

So each run is classified into three states, and only the last is a real
fairness leak:

    not offered   -> the tool is absent from tools[]
    attempted     -> called, then refused by the harness (safe by accident)
    executed      -> the call ran and reached the network

Note this reads the *same* captured requests as the availability check, just
different parts: `tools_offered()` reads the tool list (what the model *could*
use), `tool_uses()` plus `tool_results()` read the conversation history (what
it did, and whether it worked).
"""

from __future__ import annotations

import sys

from matrix import ARTIFACTS, Skip
from recording_proxy import RecordingProxy

from . import BEHAVIOR_PROMPT, PROBE_TOOLS, reached_network
from .agent_sdk import invoke as invoke_agent_sdk
from .cli import invoke as invoke_cli

DEFAULT_REPEATS = 3


def observe(proxy: RecordingProxy) -> tuple[bool, list[str]]:
    """Read one run off the captured traffic.

    Returns (was a search tool called at all, every tool that reached the net).

    The first value counts *attempts*, executed or not, because the gap between
    the two is the finding: a tool the harness offered, the model called, and
    the permission system then refused.

    The verdict deliberately keys on *any* network access rather than on the
    search tool specifically. What matters for experiment fairness is whether
    live information got in, not which door it came through — and in practice
    the model often skips search entirely and fetches a URL it already knows.
    """
    return bool(proxy.tool_uses(*PROBE_TOOLS)), reached_network(proxy)


class Scenario:
    """One configuration, run `repeats` times."""

    def __init__(self, mode: str, config: str, run, expect_network: bool, role: str):
        self.mode = mode
        self.config = config
        self.run = run                      # (proxy) -> final text, unused here
        self.expect_network = expect_network  # should this run reach the network?
        self.role = role

    def execute(self, repeats: int) -> tuple[str, str, str, bool]:
        """Returns (search attempted k/n, network reached k/n, how, ok)."""
        attempted = online = 0
        routes: list[str] = []

        for index in range(repeats):
            with RecordingProxy() as proxy:
                try:
                    self.run(proxy)
                except Skip as exc:
                    return "skipped", "-", f"missing prerequisite: {exc}", True
                called, reached = observe(proxy)
                proxy.dump(str(self._artifact(index)))

            attempted += called
            online += bool(reached)
            routes.extend(reached)

        # Expecting network access means every repeat should get online;
        # expecting none means none should. A partial count is a finding too.
        ok = online == (repeats if self.expect_network else 0)
        how = "; ".join(dict.fromkeys(routes))[:70] if routes else "none"
        return f"{attempted}/{repeats}", f"{online}/{repeats}", how, ok

    def _artifact(self, index: int):
        ARTIFACTS.mkdir(exist_ok=True)
        slug = "".join(ch if ch.isalnum() else "_"
                       for ch in f"{self.mode}_{self.config}".lower()).strip("_")[:55]
        return ARTIFACTS / f"web_search_behavior_{slug}_{index}.jsonl"


SCENARIOS = [
    Scenario(
        "claude -p", "--allowedTools WebSearch WebFetch",
        lambda p: invoke_cli(p, ["--allowedTools", "WebSearch", "WebFetch"], [],
                             BEHAVIOR_PROMPT),
        True, "POSITIVE CONTROL: pre-approved, so the web really is reachable",
    ),
    Scenario(
        "claude -p", "default",
        lambda p: invoke_cli(p, [], [], BEHAVIOR_PROMPT),
        False, "Offered and attempted, but refused for lack of approval",
    ),
    Scenario(
        "claude -p", "--disallowedTools WebSearch WebFetch",
        lambda p: invoke_cli(p, ["--disallowedTools", "WebSearch", "WebFetch"], [],
                             BEHAVIOR_PROMPT),
        False, "Never offered, so never attempted; watch for another route",
    ),
    Scenario(
        "Agent SDK", 'allowed_tools=["WebSearch","WebFetch"]',
        lambda p: invoke_agent_sdk(p, [], BEHAVIOR_PROMPT, allowed=["WebSearch", "WebFetch"]),
        True, "POSITIVE CONTROL",
    ),
    Scenario(
        "Agent SDK", "default",
        lambda p: invoke_agent_sdk(p, [], BEHAVIOR_PROMPT),
        False, "Offered and attempted, but refused for lack of approval",
    ),
    Scenario(
        "Agent SDK", 'disallowed_tools=["WebSearch","WebFetch"]',
        lambda p: invoke_agent_sdk(p, ["WebSearch", "WebFetch"], BEHAVIOR_PROMPT),
        False, "Never offered, so never attempted; watch for another route",
    ),
]


def main(repeats: int) -> int:
    rows = [(s.mode, s.config, s.role, *s.execute(repeats)) for s in SCENARIOS]

    print(f"\nProbe: {BEHAVIOR_PROMPT}\n")
    print("| Mode | Configuration | Search attempted | Network reached | How | Role |")
    print("|---|---|---|---|---|---|")
    for mode, config, role, attempted, online, how, ok in rows:
        flag = "" if ok else "  <- UNEXPECTED"
        print(f"| {mode} | `{config}` | {attempted} | {online}{flag} | {how} | {role} |")

    if any(not row[6] for row in rows if "POSITIVE CONTROL" in row[2]):
        print("\nWARNING: a positive control did not reach the network. The probe is "
              "not working, so the negative results below it prove nothing. Fix the "
              "probe before quoting these numbers.")

    return 0 if all(row[6] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REPEATS))
