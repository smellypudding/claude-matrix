"""Shared scaffolding for running a matrix and printing the result table.

Like `recording_proxy.py`, this is reused across features. Factoring out the
loop keeps each `features/<name>/<mode>.py` focused on what actually carries
information: **how this invocation mode issues a request, and which
configurations we are testing.**

One cell = one real call plus one expectation. The procedure is always the
same: start the proxy, invoke, look for the probe tool in the request body,
compare against the expectation, write the evidence to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, NamedTuple

from recording_proxy import RecordingProxy

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


class Skip(Exception):
    """This machine lacks a prerequisite (dependency or credential) for a cell.

    Kept distinct from failure: a skip does not count as a failure, but it is
    shown explicitly in the table so an unverified mode is never mistaken for
    a passing one.
    """


class Cell(NamedTuple):
    mode: str                                 # invocation mode, e.g. "claude -p"
    config: str                               # human-readable description of the config
    invoke: Callable[[RecordingProxy], None]  # issue one real call through the proxy
    expect_tool: bool                         # is the probe tool expected in the request?
    note: str                                 # takeaway, rendered into the table


class Row(NamedTuple):
    mode: str
    config: str
    verdict: str
    note: str
    ok: bool


def run_cells(cells: list[Cell], probe: tuple[str, ...], prefix: str) -> list[Row]:
    """Run each cell and return printable result rows.

    `probe` names the tools to look for; they are matched against both `name`
    and `type` prefixes — see `RecordingProxy.tools_offered` for why.
    `prefix` names the evidence files written to disk.
    """
    ARTIFACTS.mkdir(exist_ok=True)
    rows: list[Row] = []

    for index, cell in enumerate(cells):
        with RecordingProxy() as proxy:
            try:
                cell.invoke(proxy)
            except Skip as exc:
                rows.append(Row(cell.mode, cell.config, "skipped",
                                f"missing prerequisite: {exc}", True))
                continue
            except Exception as exc:  # a failed call is a finding too — record it
                rows.append(Row(cell.mode, cell.config, "FAILED",
                                f"{type(exc).__name__}: {exc}", False))
                continue

            found = bool(proxy.tools_offered(*probe))
            proxy.dump(str(ARTIFACTS / f"{prefix}_{index:02d}.jsonl"))

        ok = found == cell.expect_tool
        verdict = ("present" if found else "absent") + ("" if ok else "  <- UNEXPECTED")
        rows.append(Row(cell.mode, cell.config, verdict, cell.note, ok))

    return rows


def report(rows: list[Row], probe_label: str) -> int:
    """Print a markdown table. Returns a non-zero exit code on any surprise."""
    print(f"\n| Mode | Configuration | {probe_label} in request | Notes |")
    print("|---|---|---|---|")
    for row in rows:
        print(f"| {row.mode} | `{row.config}` | {row.verdict} | {row.note} |")
    print(f"\nRaw request bodies: {ARTIFACTS}/")
    return 0 if all(row.ok for row in rows) else 1
