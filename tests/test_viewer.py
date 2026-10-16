import json

from starlette.testclient import TestClient

import run
import viewer

START = {"seq": 0, "ts": 0.0, "kind": "start", "budget_usd": 1.0, "agents": {"ceo": {"tier": "cloud", "depth": 0}}}
MB = {"gemma4:12b": 7206}


def tool(seq, agent, name, args, result, tier="cloud", arg_labels=(), labels=()):
    return {"seq": seq, "ts": float(seq), "kind": "tool", "agent": agent, "tier": tier, "name": name,
            "args": args, "result": result, "arg_labels": list(arg_labels), "labels": list(labels)}


def check_pool(seq, agent, usd=1.0, free=10000):
    return tool(seq, agent, "check_usage", {"pool": agent},
                {"pool": agent, "api_usd": usd, "free_mb": free, "model_mb": MB})


def hire(seq, agent, name, model="gpt-4.1-mini", usd=0.1, arg_labels=()):
    return tool(seq, agent, "hire_agent",
                {"name": name, "role": "worker", "model": model, "prompt": "p", "budget_usd": usd},
                {"hired": name}, arg_labels=arg_labels)


def reply(seq, text, ts=None):
    return {"seq": seq, "ts": float(seq) if ts is None else ts, "kind": "msg", "agent": "ceo", "to": "user",
            "to_tier": "user", "text": text, "labels": [], "reply": True}


def write(folder, name, events, tail=""):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events) + tail)
    return path


def only(trace):
    [v] = trace["violations"]
    return v["rule"], [seq for seq, _ in v["evidence"]]


def test_r1_points_at_the_check_the_hire_relied_on(tmp_path):
    events = [START, check_pool(1, "ceo", free=1000), hire(2, "ceo", "w", model="ollama_chat/gemma4:12b"),
              reply(3, "failed", ts=120.0)]
    trace = viewer.load(write(tmp_path, "s1-20260101-000000", events), "phase1")
    assert (trace["name"], trace["scenario"], trace["phase"]) == ("s1-20260101-000000", "s1", "phase1")
    assert only(trace) == ("R1", [1])
    assert "7206 MB" in trace["violations"][0]["why"]
    assert trace["minutes"] == 2.0 and trace["outcome"] == "failed"


def test_r1_points_at_the_sibling_hire_that_made_the_check_stale(tmp_path):
    events = [START, check_pool(1, "ceo"), hire(2, "ceo", "m1", usd=0.3), check_pool(3, "ceo", usd=0.7),
              hire(4, "ceo", "m2", usd=0.3), check_pool(5, "m1", usd=0.3), check_pool(6, "m2", usd=0.3),
              hire(7, "m1", "w1", model="ollama_chat/gemma4:12b", usd=0.0),
              hire(8, "m2", "w2", model="ollama_chat/gemma4:12b", usd=0.0)]
    assert only(viewer.load(write(tmp_path, "s1-x", events), "phase1")) == ("R1", [6, 7])


def test_r2_points_at_the_check_and_the_spend_after_it(tmp_path):
    events = [START, check_pool(1, "ceo", usd=1.0),
              {"seq": 2, "ts": 2.0, "kind": "llm", "agent": "ceo", "cost_usd": 0.05}, hire(3, "ceo", "w", usd=1.0)]
    rules = {v["rule"]: [s for s, _ in v["evidence"]] for v in viewer.load(write(tmp_path, "s1-y", events), "x")["violations"]}
    assert rules == {"R2": [1, 2]}


def test_r3_points_at_the_private_read_and_the_label(tmp_path):
    events = [START, hire(1, "ceo", "m", model="ollama_chat/qwen3.5:4b", usd=0.0),
              tool(2, "m", "memory", {"action": "get"}, {"memories": {}}, tier="local", labels=["private"]),
              {"seq": 3, "ts": 3.0, "kind": "label", "agent": "m", "labels": ["private"]},
              {"seq": 4, "ts": 4.0, "kind": "msg", "agent": "m", "to": "ceo", "to_tier": "cloud", "text": "notes",
               "labels": ["private"], "reply": True}]
    trace = viewer.load(write(tmp_path, "s2-x", events), "phase1")
    assert [(v["seq"], v["rule"], [s for s, _ in v["evidence"]]) for v in trace["violations"] if v["rule"] == "R3"] \
        == [(4, "R3", [2, 3])]


def test_a_half_written_last_line_is_skipped(tmp_path):
    trace = viewer.load(write(tmp_path, "s3-x", [START, reply(1, "done")], tail='{"seq": 2, "ki'), "new")
    assert len(trace["events"]) == 2 and trace["outcome"] == "done"


def test_server_serves_the_page_and_every_trace(tmp_path, monkeypatch):
    write(tmp_path / "phase1", "s1-20260101-000000", [START, reply(1, "the answer")])
    write(tmp_path, "s4-20260102-000000", [START])          # a fresh run not yet moved into a phase folder
    monkeypatch.setattr(viewer, "TRACES", tmp_path)
    client = TestClient(viewer.app)
    assert "<title>" in client.get("/").text
    body = client.get("/api/runs").json()
    assert [(r["phase"], r["name"], r["outcome"]) for r in body["runs"]] == [
        ("phase1", "s1-20260101-000000", "answered in text"), ("new", "s4-20260102-000000", "no reply")]
    assert body["scenarios"] == run.SCENARIOS
    assert client.get("/nope").status_code == 404
