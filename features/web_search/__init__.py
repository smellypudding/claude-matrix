"""Feature: web search — how to actually disable it in each invocation mode.

For evaluation experiments, web search is a fairness hazard: the model may pick
up information it should not have, making results incomparable and
irreproducible. So we need to disable it in all three invocation modes, and be
able to show evidence that it is disabled.

The standard of evidence here is: **the search tool does not appear in the real
request body sent to Anthropic.** Not "the model says it didn't search", not
"it didn't search this time" — the tool was never offered at all.

    python -m features.web_search.run         # all three modes
    python -m features.web_search.cli         # claude -p only
    python -m features.web_search.agent_sdk   # Agent SDK only
    python -m features.web_search.direct_api  # direct API only
    python -m features.web_search.behavior    # behavioral cross-check (costly)

Full experimental record: docs/web_search.md

The constants below live here rather than in each mode file because they must
stay identical across modes — otherwise the cross-mode comparison is invalid.
"""

MODEL = "claude-opus-5"            # pinned, so results are comparable across modes and runs
PROMPT = "reply with exactly: OK"  # only needs to trigger one request; content is irrelevant

# The search tool takes different shapes per mode, so probe for both names:
#   claude -p / Agent SDK -> {"name": "WebSearch", ...}          no type field
#   direct API            -> {"type": "web_search_20260209", ...}
# See RecordingProxy.tools_offered for details.
PROBE_TOOLS = ("WebSearch", "web_search")
PROBE_LABEL = "Search tool"

# Probe for the behavioral cross-check (behavior.py). The Hacker News front page
# is inherently live, so the question cannot be answered from memory.
#
# SENTINEL gives the model a clean way out when it has no web access, which
# keeps it from flailing. It is deliberately *not* used as a verdict signal:
# observed runs had the model write "I'm not replying NO_SEARCH_TOOL, since
# that would be inaccurate..." while it did in fact have the tool, so any
# substring test on it reports the opposite of the truth. Verdicts come from
# captured tool calls instead.
SENTINEL = "NO_SEARCH_TOOL"
BEHAVIOR_PROMPT = (
    "Use web search to find the current top story on Hacker News and reply "
    "with just its title. If you have no web search tool available, reply "
    f"with exactly {SENTINEL} and nothing else."
)

# Probes for egress.py. Removing the web tools closes two doors, but the agent
# still has Bash, and it can delegate to a subagent. These push on both.
EGRESS_PROMPT = (
    "Fetch the page at https://news.ycombinator.com/ using a shell command and "
    "reply with the title of the first story. If you are unable to reach the "
    "network at all, reply with exactly CANNOT_REACH_NETWORK."
)
DELEGATE_PROMPT = (
    "Use the Agent tool to delegate this to a subagent: find the current top "
    "story on Hacker News. Report what the subagent returns. If neither you nor "
    "any subagent can reach the web, reply with exactly CANNOT_REACH_NETWORK."
)

# Tools that can reach the network once the dedicated web tools are gone.
# WebFetch is included because seeing it run under a disabled config would mean
# the disable itself failed.
EGRESS_TOOLS = ("Bash", "WebFetch")

# Substrings that make a Bash command a network call. Deliberately crude: this
# surfaces candidates for a human to read in the artifacts, it is not a sandbox.
EGRESS_MARKERS = ("curl", "wget", "nc ", "netcat", "urllib", "requests.get",
                  "httpx", "http.client", "Invoke-WebRequest")


def reached_network(proxy) -> list[str]:
    """Every tool call in this run that actually got out to the network.

    Shared by behavior.py and egress.py: both ultimately ask "did live
    information get in", and neither cares which door it came through.
    """
    routes: list[str] = []
    for block in proxy.executed_tool_uses(*PROBE_TOOLS, *EGRESS_TOOLS):
        name = block.get("name", "")
        args = block.get("input") or {}
        if name == "WebFetch":
            routes.append(f"WebFetch {args.get('url', '')}".strip())
        elif name == "Bash":
            command = str(args.get("command", ""))
            if any(marker in command for marker in EGRESS_MARKERS):
                routes.append(f"Bash {command[:60]}")
        else:
            routes.append(name)  # a search tool that actually ran
    return routes
