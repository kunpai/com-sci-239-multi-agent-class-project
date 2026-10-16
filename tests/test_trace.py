import json

import tracelog


def test_start_writes_jsonl(tmp_path):
    path = tmp_path / "t.jsonl"
    tracelog.start(path, task="t1", budget_usd=0.5)
    tracelog.emit("llm", task="t1", agent="ceo", text="hi")
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [e["kind"] for e in lines] == ["start", "llm"]
    assert [e["seq"] for e in lines] == [0, 1]
    assert lines[0]["budget_usd"] == 0.5


def test_start_resets_state():
    tracelog.start(None, task="t1")
    tracelog.receive("mgr", "t1", ["private"])
    tracelog.start(None, task="t2")
    assert tracelog.labels("mgr", "t1") == set()
    assert [e["kind"] for e in tracelog.events] == ["start"]


def test_rule1_sources():
    assert tracelog.SOURCES == {"read_file": ["private"], "memory": ["private"], "get_website": ["untrusted"]}


def test_rule2_labels_are_sticky_per_agent_and_task():
    tracelog.start(None, task="t1")
    tracelog.receive("mgr", "t1", ["private"])
    tracelog.receive("mgr", "t1", [])
    assert tracelog.labels("mgr", "t1") == {"private"}
    assert tracelog.labels("mgr", "t2") == set()
    assert tracelog.labels("wkr", "t1") == set()


def test_rule3_outputs_carry_sender_labels():
    tracelog.start(None, task="t1")
    tracelog.receive("mgr", "t1", ["untrusted", "private"])
    assert tracelog.outgoing("mgr", "t1", "here is the summary") == ["private", "untrusted"]


def test_rule4_exact_done_or_failed_is_clean():
    tracelog.start(None, task="t1")
    tracelog.receive("mgr", "t1", ["private"])
    assert tracelog.outgoing("mgr", "t1", "done") == []
    assert tracelog.outgoing("mgr", "t1", " failed\n") == []
    assert tracelog.outgoing("mgr", "t1", "done: the notes say X") == ["private"]


def test_label_event_only_when_set_grows():
    tracelog.start(None, task="t1")
    tracelog.receive("mgr", "t1", ["private"])
    tracelog.receive("mgr", "t1", ["private"])
    label_events = [e for e in tracelog.events if e["kind"] == "label"]
    assert len(label_events) == 1
    assert label_events[0]["agent"] == "mgr" and label_events[0]["labels"] == ["private"]
