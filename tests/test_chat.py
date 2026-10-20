import asyncio

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

import agent
import chat
import ledger
import tracelog


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """A new chat with an empty trace file and only the CEO hired."""
    path = tmp_path / "chat-20260101-000000.jsonl"
    tracelog.start(path, task="chat-x", budget_usd=0.5, models=[], agents={})
    monkeypatch.setattr(ledger, "AGENTS", {})
    ledger.add_agent("ceo", "manager", "cloud", "m", "p", None, 0, 0.5)
    monkeypatch.setattr(chat, "CHAT", {"task": "chat-x", "path": path, "history": [], "turns": [],
                                       "busy": False, "ended": False, "job": None})
    return TestClient(Starlette(routes=chat.ROUTES))


def test_state_has_the_trace_turns_and_hiring_tree(fresh):
    body = fresh.get("/chat/state").json()
    assert [e["kind"] for e in body["events"]] == ["start"]
    assert body["turns"] == [] and body["busy"] is False and body["ended"] is False
    assert body["agents"][0]["name"] == "ceo" and body["left_usd"]["ceo"] == 0.5
    assert len(body["examples"]) == 2
    assert "<title>" in fresh.get("/chat").text


def test_send_refuses_non_json_empty_and_busy(fresh):
    assert fresh.post("/chat/send", content='{"text": "hi"}', headers={"content-type": "text/plain"}).status_code == 415
    assert fresh.post("/chat/send", json={"text": "  "}).status_code == 400
    assert fresh.post("/chat/send", json=["not", "an", "object"]).status_code == 400
    chat.CHAT["busy"] = True
    assert fresh.post("/chat/send", json={"text": "hi"}).status_code == 409
    chat.CHAT.update(busy=False, ended=True)
    assert "ended" in fresh.post("/chat/send", json={"text": "hi"}).json()["error"]


def test_a_turn_records_its_events_and_feeds_history(fresh, monkeypatch):
    seen = []

    async def fake_ask(me, task, name, text):
        seen.append(text)
        tracelog.emit("msg", task=task, agent="ceo", to="w1", text="go", labels=[], reply=False)
        return "hello back"

    monkeypatch.setattr(agent, "ask_agent", fake_ask)
    asyncio.run(chat.take_turn("hi"))
    asyncio.run(chat.take_turn("again"))
    first, second = chat.CHAT["turns"]
    assert (first["start"], first["end"], first["reply"]) == (1, 2, "hello back")
    assert second["start"] == 2 and chat.CHAT["history"] == [("hi", "hello back"), ("again", "hello back")]
    assert seen[0] == "hi" and "User: hi\nYou: hello back" in seen[1]
    assert chat.CHAT["busy"] is False and chat.CHAT["ended"] is False


def test_a_failed_turn_ends_the_chat(fresh, monkeypatch):
    async def timeout(me, task, name, text):
        return "error: ceo failed: timed out"

    monkeypatch.setattr(agent, "ask_agent", timeout)
    asyncio.run(chat.take_turn("hi"))
    assert chat.CHAT["ended"] is True and chat.CHAT["history"] == []
    assert chat.CHAT["turns"][0]["reply"].startswith("error: ")
