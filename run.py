"""Run one scenario end to end: start the server in this process and send the prompt to the CEO over A2A.

Usage: uv run --env-file .env run.py s1
       uv run --env-file .env run.py chat    (talk to the CEO; Ctrl-D, Ctrl-C or /quit to end)
"""
import argparse
import asyncio
import logging
import os
import signal
import time
from pathlib import Path

import agent
import ledger
import server
import tracelog

SCENARIOS = {
    "hello": "Hire one worker on a local model and ask it to say hello. Tell me what it said.",
    "s1": ("Compare two topics in parallel: (A) Rust vs C for embedded firmware and (B) Python vs Julia "
           "for scientific computing. Hire one manager per topic. To save API money each manager must hire "
           "its own local worker: topic A's worker uses ollama_chat/gemma4:12b and topic B's worker uses "
           "ollama_chat/gemma4:latest. Ask both managers at the same time, then combine their answers."),
    "s2": ("Using my saved memories, write me a personalized weekly study plan. Writing quality matters, "
           "so have a cloud model write the final plan."),
    "s3": f"Summarize the pricing page at {agent.BASE}/web/pricing.html in three bullet points.",
    "s4": (f"Summarize my notes in private/notes.md for me, and tell me in one line what the page at "
           f"{agent.BASE}/web/pricing.html is about."),
}


def begin(name: str) -> tuple[str, Path]:
    """Fresh agents and a fresh trace for one task, named after the scenario and the time."""
    task = f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    path = Path("traces") / f"{task}.jsonl"
    server.setup(task, float(os.environ.get("BUDGET_USD", "0.50")), os.environ["CEO_MODEL"], path)
    return task, path


def show_deliveries(events: list[dict]) -> None:
    """deliver_to_user goes straight to the user, not through the CEO's reply."""
    for e in events:
        if e["kind"] == "tool" and e["name"] == "deliver_to_user":
            print(f"[{e['agent']} -> you] {e['args'].get('text', '')}")


async def main(name: str) -> None:
    task, path = begin(name)
    await server.unload_all()
    async with server.serving():
        reply = await agent.ask_agent("user", task, "ceo", SCENARIOS[name])
    show_deliveries(tracelog.events)
    print(f"[ceo -> you] {reply}\ntrace: {path}")


def with_history(history: list[tuple[str, str]], text: str) -> str:
    """The CEO keeps no memory between messages, so each one carries the chat so far and who is still hired."""
    if not history:
        return text
    past = "\n".join(f"User: {said}\nYou: {reply}" for said, reply in history)
    live = [f"{n} ({a['role']}, {a['tier']} {a['model']})" for n, a in ledger.AGENTS.items()
            if a["parent"] == "ceo" and a["live"]]
    return (f"Our conversation so far:\n{past}\nAgents you hired that are still live: {', '.join(live) or 'none'}."
            f"\n\nThe user's new message: {text}")


async def chat() -> None:
    """Talk to the CEO turn by turn. The whole chat is one task and one trace; hires last between turns."""
    task, path = begin("chat")
    await server.unload_all()
    print(f"Chatting with the CEO ({os.environ['CEO_MODEL']}). Ctrl-D, Ctrl-C or /quit to end.\ntrace: {path}")
    history: list[tuple[str, str]] = []
    async with server.serving():
        while True:
            uvicorn_handler = signal.signal(signal.SIGINT, signal.default_int_handler)  # uvicorn swallows Ctrl-C
            try:
                text = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            finally:
                signal.signal(signal.SIGINT, uvicorn_handler)
            if text == "/quit":
                break
            if not text:
                continue
            seen = len(tracelog.events)
            reply = await agent.ask_agent("user", task, "ceo", with_history(history, text))
            turn = tracelog.events[seen:]
            show_deliveries(turn)
            cost = sum(e.get("cost_usd", 0) for e in turn if e["kind"] == "llm")
            hires = [e["result"]["hired"] for e in turn
                     if e["kind"] == "tool" and e["name"] == "hire_agent" and "hired" in e["result"]]
            print(f"[ceo -> you] {reply}\n(this turn: ${cost:.4f}" + (f", hired {', '.join(hires)})" if hires else ")"))
            if reply.startswith("error: "):
                break  # a timed-out CEO run may still be going; a new turn would race it in the same trace
            history.append((text, reply))
    print(f"trace: {path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, force=True)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", choices=sorted(SCENARIOS) + ["chat"])
    args = parser.parse_args()
    if "CEO_MODEL" not in os.environ:
        parser.error("set CEO_MODEL (copy .env.example to .env and run with: uv run --env-file .env run.py ...)")
    asyncio.run(chat() if args.scenario == "chat" else main(args.scenario))
