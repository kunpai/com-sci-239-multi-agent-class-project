"""Trace viewer: a web page with every trace in traces/ and its R1-R5 violations marked.

Usage: uv run viewer.py            # then open http://127.0.0.1:8239
"""
import argparse
import json
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

import policy
import run
from tracelog import PRIVATE, UNTRUSTED

ROOT = Path(__file__).parent
TRACES = ROOT / "traces"
PAGE = ROOT / "viewer.html"


def _own_check(e: dict, me: str) -> bool:
    return (policy._tool(e, "check_usage") and e["agent"] == me and e["args"].get("pool") == me
            and "error" not in e.get("result", {}))


def evidence(prefix: list[dict], e: dict, why: str) -> list[tuple[int, str]]:
    """The earlier events a violation rests on, found the same way policy.py decides it."""
    rule, me, found = why[:2], e.get("agent", ""), {}
    if rule == "R1":
        turn = e.get("turn")
        for p in reversed(prefix):
            if _own_check(p, me):
                if turn is not None and p["seq"] > turn:
                    continue  # issued in the same LLM turn as the hire, so never seen
                r = p["result"]
                found[p["seq"]] = f"{me}'s last check of its own pool: ${r['api_usd']} left, {r['free_mb']:,} MB free"
                break
            if not found and policy._hire(p) and (p["agent"] == me or policy._local_hire(p)):
                found[p["seq"]] = f"{p['agent']} hired {p['args'].get('model')} after that check"
    elif rule == "R2":
        for name in why.split("over budget: ", 1)[1].split(", "):
            last = next((p for p in reversed(prefix) if _own_check(p, name)), None)
            if last:
                found[last["seq"]] = f"{name}'s last check: ${last['result']['api_usd']} left"
                for p in prefix:
                    if p["seq"] > last["seq"] and p["kind"] == "llm" and p["agent"] == name and p.get("cost_usd"):
                        found[p["seq"]] = f"{name} spends ${p['cost_usd']:.4f} on a turn after that check"
    elif rule in ("R3", "R4"):
        label = PRIVATE if rule == "R3" else UNTRUSTED
        src = next((p for p in prefix if p["kind"] == "tool" and label in p.get("labels", [])), None)
        if src:
            found[src["seq"]] = f"{src['agent']} reads {label} data with {src['name']}"
        got = next((p for p in prefix if p["kind"] == "label" and p["agent"] == me and label in p["labels"]), None)
        if got:
            found[got["seq"]] = f"{me} starts holding {label}"
    return sorted(found.items())


def outcome(events: list[dict]) -> str:
    replies = [e["text"].strip() for e in events if e["kind"] == "msg" and e.get("to") == "user"]
    if not replies:
        return "no reply"
    return replies[-1] if replies[-1] in ("done", "failed") else "answered in text"


def load(path: Path, phase: str) -> dict:
    """One trace with its violations. A half-written last line (a run still going) is skipped."""
    events = []
    for line in path.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    found = [{"seq": e["seq"], "rule": why[:2], "why": why.split(": ", 1)[1], "evidence": evidence(events[:i], e, why)}
             for i, e in enumerate(events) for why in policy.violations(events[:i], e)]
    return {"name": path.stem, "phase": phase, "scenario": path.stem.split("-")[0], "events": events,
            "violations": found, "outcome": outcome(events),
            "cost": sum(e.get("cost_usd") or 0 for e in events if e["kind"] == "llm"),
            "minutes": (events[-1]["ts"] - events[0]["ts"]) / 60 if events else 0.0}


def runs() -> list[dict]:
    """Every trace under traces/. One sitting directly in traces/ is a fresh run, labelled 'new'."""
    out = []
    for path in sorted(TRACES.rglob("*.jsonl")):
        folder = path.parent.relative_to(TRACES).as_posix()
        out.append(load(path, "new" if folder == "." else folder))
    return out


def page(request: Request) -> FileResponse:
    return FileResponse(PAGE)


def api_runs(request: Request) -> JSONResponse:
    return JSONResponse({"runs": runs(), "scenarios": run.SCENARIOS})


app = Starlette(routes=[Route("/", page), Route("/api/runs", api_runs)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8239)
    args = parser.parse_args()
    print(f"trace viewer at http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
