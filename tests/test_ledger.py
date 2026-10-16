import ledger


def accounts(**overrides):
    base = {"ceo": {"parent": None, "reserved": 1.0, "spent": 0.1, "live": True},
            "mgr": {"parent": "ceo", "reserved": 0.4, "spent": 0.05, "live": True},
            "wkr": {"parent": "mgr", "reserved": 0.1, "spent": 0.02, "live": True}}
    for name, fields in overrides.items():
        base[name] = {**base[name], **fields}
    return base


def test_live_children_hold_their_reservation():
    left = ledger.left(accounts())
    assert round(left["ceo"], 6) == 0.5      # 1.0 - 0.1 spent - 0.4 held by mgr
    assert round(left["mgr"], 6) == 0.25     # 0.4 - 0.05 - 0.1 held by wkr
    assert round(left["wkr"], 6) == 0.08


def test_fired_subtree_holds_everything_it_spent():
    left = ledger.left(accounts(mgr={"live": False}, wkr={"live": False}))
    assert round(left["ceo"], 6) == 0.83     # 1.0 - 0.1 - (0.05 by mgr + 0.02 by wkr): spend below is not refunded


def test_fire_does_not_refund_spend_below():
    events = [
        {"kind": "start", "budget_usd": 0.5},
        {"kind": "tool", "agent": "ceo", "name": "hire_agent",
         "args": {"name": "m1", "budget_usd": 0.3}, "result": {"hired": "m1"}},
        {"kind": "tool", "agent": "m1", "name": "hire_agent",
         "args": {"name": "w1", "budget_usd": 0.2}, "result": {"hired": "w1"}},
        {"kind": "llm", "agent": "w1", "cost_usd": 0.15},
        {"kind": "tool", "agent": "ceo", "name": "fire_agent",
         "args": {"name": "m1"}, "result": {"fired": ["m1", "w1"]}},
    ]
    assert round(ledger.left(ledger.replay(events))["ceo"], 6) == 0.35


def test_overspend_shows_as_negative():
    assert ledger.left(accounts(wkr={"spent": 0.3}))["wkr"] < 0


def test_replay_rebuilds_accounts_from_trace():
    events = [
        {"kind": "start", "budget_usd": 1.0},
        {"kind": "llm", "agent": "ceo", "cost_usd": 0.1},
        {"kind": "tool", "agent": "ceo", "name": "hire_agent",
         "args": {"name": "mgr", "budget_usd": 0.4}, "result": {"hired": "mgr"}},
        {"kind": "tool", "agent": "ceo", "name": "hire_agent",
         "args": {"name": "bad", "budget_usd": 9}, "result": {"error": "unknown model"}},
        {"kind": "llm", "agent": "mgr", "cost_usd": 0.05},
        {"kind": "tool", "agent": "ceo", "name": "fire_agent",
         "args": {"name": "mgr"}, "result": {"fired": ["mgr"]}},
    ]
    accts = ledger.replay(events)
    assert set(accts) == {"ceo", "mgr"}
    assert accts["mgr"]["live"] is False
    assert round(ledger.left(accts)["ceo"], 6) == 0.85


def test_replay_counts_a_proposed_hire():
    events = [{"kind": "start", "budget_usd": 1.0},
              {"kind": "tool", "agent": "ceo", "name": "hire_agent", "args": {"name": "w", "budget_usd": "0.3"}}]
    assert round(ledger.left(ledger.replay(events))["ceo"], 6) == 0.7


def test_add_agent_registers_record():
    ledger.AGENTS.clear()
    rec = ledger.add_agent("w1", "worker", "cloud", "gpt-4.1-mini", "Say hi", "ceo", 1, 0.1)
    assert ledger.AGENTS["w1"] is rec
    assert rec["live"] and rec["spent"] == 0.0 and rec["gpu_mb"] == 0
    ledger.AGENTS.clear()


def test_free_mb_is_positive():
    assert ledger.free_mb() > 0
