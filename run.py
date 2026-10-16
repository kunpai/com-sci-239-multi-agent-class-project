"""Run one scenario end to end: start the server in this process and send the prompt to the CEO over A2A.

Usage: uv run --env-file .env run.py s1
"""
import argparse
import asyncio
import logging
import os
import time
from pathlib import Path

import agent
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


async def main(name: str) -> None:
    task = f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    path = Path("traces") / f"{task}.jsonl"
    server.setup(task, float(os.environ.get("BUDGET_USD", "0.50")), os.environ["CEO_MODEL"], path)
    await server.unload_all()
    async with server.serving():
        reply = await agent.ask_agent("user", task, "ceo", SCENARIOS[name])
    for e in tracelog.events:
        if e["kind"] == "tool" and e["name"] == "deliver_to_user":
            print(f"[{e['agent']} -> you] {e['args'].get('text', '')}")
    print(f"[ceo -> you] {reply}\ntrace: {path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, force=True)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    args = parser.parse_args()
    if "CEO_MODEL" not in os.environ:
        parser.error("set CEO_MODEL (copy .env.example to .env and run with: uv run --env-file .env run.py ...)")
    asyncio.run(main(args.scenario))
