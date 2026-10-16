import asyncio
from types import SimpleNamespace

import agent
import ledger
import tracelog


def test_system_prompt_worker_vs_manager():
    worker = {"name": "w1", "role": "worker", "prompt": "Summarize."}
    mgr = {"name": "m1", "role": "manager", "prompt": "Research X."}
    assert agent.system_prompt(worker) == "Summarize."
    text = agent.system_prompt(mgr)
    assert "your pool is 'm1'" in text and "Policies you must follow" in text and text.endswith("Research X.")


def test_to_openai_hides_caller():
    tool = SimpleNamespace(name="check_usage", description="d", input_schema={
        "type": "object", "properties": {"caller": {"type": "string"}, "pool": {"type": "string"}},
        "required": ["caller", "pool"]})
    fn = agent.to_openai(tool)["function"]
    assert fn["name"] == "check_usage"
    assert list(fn["parameters"]["properties"]) == ["pool"]
    assert fn["parameters"]["required"] == ["pool"]


def result(text, is_error=False):
    return SimpleNamespace(content=[SimpleNamespace(text=text)], is_error=is_error, structured_content=None)


def test_unpack_json_and_errors():
    assert agent.unpack(result('{"api_usd": 0.5}')) == {"api_usd": 0.5}
    assert agent.unpack(result("Error executing tool: bad args", is_error=True)) == {
        "error": "Error executing tool: bad args"}


def test_dispatch_rejects_malformed_arguments_without_calling_tools():
    for bad in ["{not json", "[1, 2]"]:
        call = SimpleNamespace(id="c1", function=SimpleNamespace(name="check_usage", arguments=bad))
        out = asyncio.run(agent.dispatch(None, "ceo", "t1", call))  # session=None: must never be touched
        assert "error" in out


def test_ask_unknown_or_fired_agent_returns_error_without_network():
    ledger.AGENTS.clear()
    tracelog.start(None, task="t1")
    ledger.add_agent("w1", "worker", "cloud", "gpt-4.1-mini", "x", "ceo", 1, 0.1)
    ledger.AGENTS["w1"]["live"] = False
    assert asyncio.run(agent.ask_agent("ceo", "t1", "nobody", "hi")).startswith("error")
    assert asyncio.run(agent.ask_agent("ceo", "t1", "w1", "hi")).startswith("error")
    assert not [e for e in tracelog.events if e["kind"] == "msg"]
    ledger.AGENTS.clear()


def test_ask_agent_traces_and_moves_labels(monkeypatch):
    ledger.AGENTS.clear()
    tracelog.start(None, task="t1")
    ledger.add_agent("ceo", "manager", "cloud", "gpt-4.1-mini", "boss", None, 0, 1.0)
    ledger.add_agent("m1", "manager", "local", "ollama_chat/tiny", "notes", "ceo", 1, 0.0)

    async def fake_send(name, text, task):
        tracelog.receive("m1", "t1", ["private"])  # m1 read memory while working
        return "your notes say X"
    monkeypatch.setattr(agent, "a2a_send", fake_send)
    assert asyncio.run(agent.ask_agent("ceo", "t1", "m1", "summarize my notes")) == "your notes say X"
    msgs = [e for e in tracelog.events if e["kind"] == "msg"]
    assert [(m["agent"], m["to"], m["to_tier"], m["labels"]) for m in msgs] == [
        ("ceo", "m1", "local", []), ("m1", "ceo", "cloud", ["private"])]
    assert tracelog.labels("ceo", "t1") == {"private"}   # Phase 1 records the leak; it does not block it
    ledger.AGENTS.clear()
