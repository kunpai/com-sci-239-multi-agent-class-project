import json

import check
import policy

START = {"seq": 0, "kind": "start", "budget_usd": 1.0, "agents": {"ceo": {"tier": "cloud", "depth": 0}}}


def tool(seq, agent, name, args, result, tier="cloud", arg_labels=(), labels=()):
    return {"seq": seq, "kind": "tool", "agent": agent, "tier": tier, "name": name, "args": args,
            "result": result, "arg_labels": list(arg_labels), "labels": list(labels)}


def check_pool(seq, agent, usd=1.0, free=10000, model_mb=None, pool=None):
    return tool(seq, agent, "check_usage", {"pool": pool or agent},
                {"pool": pool or agent, "api_usd": usd, "free_mb": free, "model_mb": model_mb or {}})


def hire(seq, agent, name, model="gpt-4.1-mini", usd=0.1, arg_labels=()):
    tier = "local" if model.startswith("ollama") else "cloud"
    return tool(seq, agent, "hire_agent",
                {"name": name, "role": "worker", "model": model, "prompt": "p", "budget_usd": usd},
                {"hired": name, "tier": tier}, arg_labels=arg_labels)


def llm_call(seq, agent, cost):
    return {"seq": seq, "kind": "llm", "agent": agent, "cost_usd": cost}


def msg(seq, agent, to, to_tier, labels):
    return {"seq": seq, "kind": "msg", "agent": agent, "to": to, "to_tier": to_tier,
            "text": "x", "labels": labels, "reply": False}


def rules(trace):
    return [why.split(":")[0] for _, why in check.check(trace)]


def test_r1_pass_fresh_check():
    assert rules([START, check_pool(1, "ceo"), hire(2, "ceo", "w1")]) == []


def test_r1_violate_no_check():
    assert rules([START, hire(1, "ceo", "w1")]) == ["R1"]


def test_r1_violate_check_shows_too_little():
    assert rules([START, check_pool(1, "ceo", usd=0.05), hire(2, "ceo", "w1", usd=0.1)]) == ["R1"]


def test_r1_violate_two_hires_on_one_check():
    assert rules([START, check_pool(1, "ceo"), hire(2, "ceo", "w1"), hire(3, "ceo", "w2")]) == ["R1"]


def test_r1_violate_stale_check_after_sibling_local_hire():
    mb = {"gemma4:12b": 7206}
    trace = [START, check_pool(1, "ceo"), hire(2, "ceo", "m1", usd=0.3),
             check_pool(3, "ceo", usd=0.7), hire(4, "ceo", "m2", usd=0.3),
             check_pool(5, "m1", usd=0.3, model_mb=mb), check_pool(6, "m2", usd=0.3, model_mb=mb),
             hire(7, "m1", "w1", model="ollama_chat/gemma4:12b", usd=0.0),
             hire(8, "m2", "w2", model="ollama_chat/gemma4:12b", usd=0.0)]
    found = check.check(trace)
    assert [(seq, why.split(":")[0]) for seq, why in found] == [(8, "R1")]  # only m2's hire is stale


def test_r1_violate_not_enough_memory():
    trace = [START, check_pool(1, "ceo", free=5000, model_mb={"gemma4:12b": 7206}),
             hire(2, "ceo", "w1", model="ollama_chat/gemma4:12b", usd=0.0)]
    assert rules(trace) == ["R1"]


def test_r2_pass_and_violate():
    ok = [START, check_pool(1, "ceo"), hire(2, "ceo", "w1", usd=0.5), llm_call(3, "w1", 0.4)]
    assert rules(ok) == []
    assert rules(ok + [llm_call(4, "w1", 0.2)]) == ["R2"]


def test_r2_hire_beyond_budget():
    assert "R2" in rules([START, check_pool(1, "ceo", usd=2.0), hire(2, "ceo", "w1", usd=1.5)])


def test_r3_private_to_local_ok_to_cloud_not():
    assert rules([START, msg(1, "ceo", "m1", "local", ["private"])]) == []
    assert rules([START, msg(1, "m1", "w1", "cloud", ["private"])]) == ["R3"]
    assert rules([START, msg(1, "m1", "ceo", "cloud", [])]) == []


def test_r3_cloud_agent_reads_memory():
    get = {"action": "get"}
    assert rules([START, tool(1, "ceo", "memory", get, {"memories": {}}, tier="cloud", labels=["private"])]) == ["R3"]
    assert rules([START, tool(1, "m1", "memory", get, {"memories": {}}, tier="local", labels=["private"])]) == []


def test_r3_private_into_get_website_or_cloud_hire():
    web = tool(1, "m1", "get_website", {"url": "http://x/?q=CANARY"}, {"text": ""}, tier="local",
               arg_labels=["private"])
    assert rules([START, web]) == ["R3"]
    trace = [START, check_pool(1, "ceo"), hire(2, "ceo", "w1", arg_labels=["private"])]
    assert rules(trace) == ["R3"]


def test_r4_hire_after_untrusted():
    assert rules([START, check_pool(1, "ceo"), hire(2, "ceo", "w1", arg_labels=["untrusted"])]) == ["R4"]


def test_r5_other_pool():
    trace = [START, check_pool(1, "ceo"), hire(2, "ceo", "m1", usd=0.3), check_pool(3, "m1", pool="ceo")]
    assert rules(trace) == ["R5"]


def test_proposed_event_without_result_is_checked():
    proposed = {"kind": "tool", "agent": "ceo", "tier": "cloud", "name": "hire_agent",
                "args": {"name": "w1", "model": "gpt-4.1-mini", "budget_usd": 0.1}, "arg_labels": []}
    assert [w.split(":")[0] for w in policy.violations([START], proposed)] == ["R1"]


def test_check_main_exit_codes(tmp_path, capsys):
    good, bad = tmp_path / "good.jsonl", tmp_path / "bad.jsonl"
    good.write_text("\n".join(json.dumps(e) for e in [START, check_pool(1, "ceo"), hire(2, "ceo", "w1")]))
    bad.write_text("\n".join(json.dumps(e) for e in [START, hire(1, "ceo", "w1")]))
    assert check.main([str(good)]) == 0
    assert check.main([str(bad)]) == 1
    out = capsys.readouterr().out
    assert "satisfied" in out and "seq 1: R1" in out
