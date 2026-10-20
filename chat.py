"""Chat with the CEO in a browser. The full trace shows live in the viewer's Chat tab.

Usage: uv run --env-file .env chat.py      # then open http://127.0.0.1:9100/chat
"""
import asyncio
import json
import logging
import os
from pathlib import Path

from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

import agent
import ledger
import run
import server
import tracelog
import viewer

PAGE = Path(__file__).parent / "chat.html"
AGENT_FIELDS = ("name", "role", "tier", "model", "parent", "live", "reserved", "spent", "gpu_mb")

# One chat per process: one task, one trace, one budget. Hires last between turns, as in `run.py chat`.
CHAT: dict = {"task": "", "path": None, "history": [], "turns": [], "busy": False, "ended": False, "job": None}


async def take_turn(text: str) -> None:
    """Send one user message to the CEO and record which trace events belong to this turn."""
    turn = {"text": text, "start": len(tracelog.events), "end": None, "reply": None}
    CHAT["turns"].append(turn)
    try:
        reply = await agent.ask_agent("user", CHAT["task"], "ceo", run.with_history(CHAT["history"], text))
    except Exception as exc:  # noqa: BLE001 - show any failure in the chat rather than losing the turn
        reply = f"error: {type(exc).__name__}: {exc}"
    turn.update(end=len(tracelog.events), reply=reply)
    if reply.startswith("error: "):
        CHAT["ended"] = True  # a timed-out CEO run may still be going; a new turn would race it (see run.chat)
    else:
        CHAT["history"].append((text, reply))
    CHAT["busy"] = False


def page(request: Request) -> FileResponse:
    return FileResponse(PAGE)


async def send(request: Request) -> JSONResponse:
    """Start a turn. JSON only, so another site open in the browser can't post here and spend the budget."""
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return JSONResponse({"error": "send JSON"}, status_code=415)
    try:
        text = str((await request.json()).get("text", "")).strip()
    except (json.JSONDecodeError, AttributeError):
        return JSONResponse({"error": "send {\"text\": ...}"}, status_code=400)
    if CHAT["ended"]:
        return JSONResponse({"error": "this chat has ended; restart chat.py for a new one"}, status_code=409)
    if CHAT["busy"]:
        return JSONResponse({"error": "the CEO is still working on your last message"}, status_code=409)
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)
    CHAT["busy"] = True
    CHAT["job"] = asyncio.create_task(take_turn(text))  # keep a reference so the task is not garbage-collected
    return JSONResponse({"ok": True})


async def state(request: Request) -> JSONResponse:
    """Everything the page draws: turns, the trace so far with its violations, and the hiring tree.

    Async with no await inside, so it runs on the event loop between agent steps and sees one consistent
    snapshot (a sync endpoint would run in a worker thread while hires change ledger.AGENTS)."""
    trace = viewer.load(CHAT["path"], "new")
    return JSONResponse({
        "task": CHAT["task"], "trace": str(CHAT["path"]), "busy": CHAT["busy"], "ended": CHAT["ended"],
        "turns": CHAT["turns"], "events": trace["events"], "violations": trace["violations"],
        "agents": [{k: a[k] for k in AGENT_FIELDS} for a in ledger.AGENTS.values()],
        "left_usd": ledger.left(ledger.AGENTS), "examples": [run.SCENARIOS["hello"], run.SCENARIOS["s3"]],
    })


ROUTES = [Route("/chat", page), Route("/chat/state", state), Route("/chat/send", send, methods=["POST"])]


async def main() -> None:
    CHAT["task"], CHAT["path"] = run.begin("chat")
    await server.unload_all()
    server.app.router.routes.extend(ROUTES)
    # The chat stays up for hours: refuse other Host names so a DNS-rebinding page can't read or post here
    server.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    async with server.serving():
        print(f"chat at {agent.BASE}/chat (Ctrl-C to stop)\ntrace: {CHAT['path']}")
        await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, force=True)
    if "CEO_MODEL" not in os.environ:
        raise SystemExit("set CEO_MODEL (copy .env.example to .env and run with: uv run --env-file .env chat.py)")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # uvicorn stops on Ctrl-C, then re-raises it
        print(f"\ntrace: {CHAT['path']}")
