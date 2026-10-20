import agent
import ledger
import run


def test_scenarios_exist_and_point_at_the_local_page():
    assert set(run.SCENARIOS) == {"hello", "s1", "s2", "s3", "s4"}
    assert f"{agent.BASE}/web/pricing.html" in run.SCENARIOS["s3"]
    assert "ollama_chat/gemma4:12b" in run.SCENARIOS["s1"] and "ollama_chat/gemma4:latest" in run.SCENARIOS["s1"]
    assert "private/notes.md" in run.SCENARIOS["s4"]


def test_chat_first_message_goes_through_unchanged():
    assert run.with_history([], "hi") == "hi"


def test_chat_carries_history_and_live_hires(monkeypatch):
    monkeypatch.setattr(ledger, "AGENTS", {
        "ceo": {"role": "manager", "tier": "cloud", "model": "m", "parent": None, "live": True},
        "w1": {"role": "worker", "tier": "local", "model": "ollama_chat/qwen3.5:4b", "parent": "ceo", "live": True},
        "w2": {"role": "worker", "tier": "local", "model": "ollama_chat/qwen3.5:4b", "parent": "ceo", "live": False},
    })
    prompt = run.with_history([("hire a worker", "hired w1")], "ask it again")
    assert "User: hire a worker\nYou: hired w1" in prompt
    assert "w1 (worker, local ollama_chat/qwen3.5:4b)" in prompt and "w2" not in prompt
    assert prompt.endswith("The user's new message: ask it again")


def test_chat_says_none_when_every_hire_was_fired(monkeypatch):
    monkeypatch.setattr(ledger, "AGENTS", {
        "w1": {"role": "worker", "tier": "local", "model": "m", "parent": "ceo", "live": False},
    })
    assert "Agents you hired that are still live: none." in run.with_history([("a", "b")], "c")
