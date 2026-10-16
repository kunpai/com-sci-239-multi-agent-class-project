"""End to end with a scripted LLM: real MCP and A2A on a test port, no tokens spent.

The MCP app can be served only once per process, so this file holds the only test that serves it.
"""
import asyncio
import json
from types import SimpleNamespace

import agent
import ledger
import llm
import server

PORT = 9199


def call(name, args, cid):
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def reply(content="", calls=None):
    return SimpleNamespace(content=content, tool_calls=calls)


async def fake_chat(model, messages, tools=None):
    """Scripted CEO: check, hire a worker, ask it, finish. The worker says hello."""
    if messages[0]["content"] == "Greet people.":
        return reply("hello from w1"), 0.001
    turn = sum(1 for m in messages if m["role"] == "tool")
    script = [reply(calls=[call("check_usage", {"pool": "ceo"}, "c1")]),
              reply(calls=[call("hire_agent", {"name": "w1", "role": "worker", "model": "gpt-4.1-mini",
                                               "prompt": "Greet people.", "budget_usd": 0.1}, "c2")]),
              reply(calls=[call("ask_agent", {"name": "w1", "text": "say hello"}, "c3")]),
              reply("w1 says: hello from w1")]
    return script[turn], 0.002


def test_ceo_hires_asks_and_traces(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "PORT", PORT)
    monkeypatch.setattr(agent, "BASE", f"http://127.0.0.1:{PORT}")
    monkeypatch.setattr(server, "MODELS", ["gpt-4.1-mini"])
    monkeypatch.setattr(llm, "chat", fake_chat)
    path = tmp_path / "smoke.jsonl"
    server.setup("t-smoke", 0.5, "gpt-4.1-mini", path)

    async def go():
        async with server.serving():
            return await agent.ask_agent("user", "t-smoke", "ceo", "Get a greeting.")

    assert asyncio.run(go()) == "w1 says: hello from w1"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[0]["kind"] == "start"
    assert [e["name"] for e in events if e["kind"] == "tool"] == ["check_usage", "hire_agent"]
    assert [(e["agent"], e["to"]) for e in events if e["kind"] == "msg"] == [
        ("user", "ceo"), ("ceo", "w1"), ("w1", "ceo"), ("ceo", "user")]
    check = next(e for e in events if e["kind"] == "tool" and e["name"] == "check_usage")
    assert check["result"]["api_usd"] == 0.498          # 0.5 minus the CEO's first LLM call
    assert ledger.AGENTS["w1"]["spent"] == 0.001
    assert round(ledger.left(ledger.AGENTS)["ceo"], 6) == round(0.5 - 4 * 0.002 - 0.1, 6)
