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

Full experimental record: docs/web_search.md

The constants below live here rather than in each mode file because they must
stay identical across modes — otherwise the cross-mode comparison is invalid.
"""

MODEL = "claude-opus-5"            # pinned, so results are comparable across modes and runs
PROMPT = "reply with exactly: OK"  # only needs to trigger one request; content is irrelevant

# The search tool takes different shapes per mode, so probe for both names:
#   claude -p / Agent SDK -> {"name": "WebSearch", ...}          no type field
#   direct API            -> {"type": "web_search_20260209", ...}
# See RecordingProxy.tool_calls_for for details.
PROBE_TOOLS = ("WebSearch", "web_search")
PROBE_LABEL = "Search tool"
