import asyncio

import pytest

import ledger
import server


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    ledger.AGENTS.clear()
    monkeypatch.setattr(server, "MODELS", ["gpt-4.1-mini", "ollama_chat/tiny"])
    monkeypatch.setattr(server, "mount", lambda rec: None)
    monkeypatch.setattr(server, "unmount", lambda name: None)
    ledger.add_agent("ceo", "manager", "cloud", "gpt-4.1-mini", "boss", None, 0, 1.0)
    yield
    ledger.AGENTS.clear()


def hire(**kw):
    args = {"caller": "ceo", "name": "w1", "role": "worker", "model": "gpt-4.1-mini",
            "prompt": "p", "budget_usd": 0.2} | kw
    return asyncio.run(server.hire_agent(**args))


def test_hire_reserves_budget_from_hirer():
    out = hire()
    assert out == {"hired": "w1", "tier": "cloud", "depth": 1, "reserved_usd": 0.2, "gpu_mb": 0}
    assert ledger.AGENTS["w1"]["parent"] == "ceo"
    assert round(ledger.left(ledger.AGENTS)["ceo"], 6) == 0.8


@pytest.mark.parametrize("bad", [{"model": "nope"}, {"role": "boss"}, {"name": "Bad Name"}, {"name": "ceo"}])
def test_hire_rejects_structural_errors(bad):
    assert "error" in hire(**bad)


def test_depth_cap():
    hire(name="m1", role="manager")
    assert hire(caller="m1", name="w2")["depth"] == 2
    assert "error" in hire(caller="w2", name="w3")


def test_concurrent_hires_with_same_name_only_one_wins(monkeypatch):
    async def slow_load(model):
        await asyncio.sleep(0.05)
        return 100
    monkeypatch.setattr(server, "ollama_load", slow_load)

    async def both():
        args = {"caller": "ceo", "name": "w1", "role": "worker", "model": "ollama_chat/tiny",
                "prompt": "p", "budget_usd": 0.1}
        return await asyncio.gather(server.hire_agent(**args), server.hire_agent(**args))

    results = asyncio.run(both())
    assert sorted("hired" in r for r in results) == [False, True]
    assert ledger.AGENTS["w1"]["gpu_mb"] == 100


def test_failed_model_load_releases_the_name(monkeypatch):
    async def broken_load(model):
        raise server.httpx.ConnectError("ollama is not running")
    monkeypatch.setattr(server, "ollama_load", broken_load)
    assert "error" in hire(model="ollama_chat/tiny")
    assert "w1" not in ledger.AGENTS


def test_fire_takes_the_whole_subtree():
    hire(name="m1", role="manager", budget_usd=0.5)
    hire(caller="m1", name="w2", budget_usd=0.1)
    assert asyncio.run(server.fire_agent(caller="ceo", name="m1")) == {"fired": ["m1", "w2"]}
    assert not ledger.AGENTS["m1"]["live"] and not ledger.AGENTS["w2"]["live"]
    assert round(ledger.left(ledger.AGENTS)["ceo"], 6) == 1.0  # nothing was spent, so everything returns
    assert "error" in asyncio.run(server.fire_agent(caller="ceo", name="ceo"))


def test_check_usage_reports_money_and_memory(monkeypatch):
    async def sizes():
        return {"tiny": 50}
    monkeypatch.setattr(server, "model_sizes", sizes)
    out = asyncio.run(server.check_usage(caller="ceo", pool="ceo"))
    assert out["api_usd"] == 1.0 and out["free_mb"] > 0 and out["model_mb"] == {"tiny": 50}
    assert "error" in asyncio.run(server.check_usage(caller="ceo", pool="nobody"))


def test_model_sizes_skips_ollama_when_no_local_models(monkeypatch):
    monkeypatch.setattr(server, "MODELS", ["gpt-4.1-mini"])
    assert asyncio.run(server.model_sizes()) == {}


def test_read_file_stays_inside_data(monkeypatch, tmp_path):
    data = tmp_path / "data"
    (data / "private").mkdir(parents=True)
    (data / "private" / "notes.md").write_text("secret")
    (tmp_path / "outside.txt").write_text("nope")
    monkeypatch.setattr(server, "DATA", data)
    assert server.read_file(caller="m1", path="private/notes.md")["text"] == "secret"
    for bad in ["../outside.txt", str(tmp_path / "outside.txt"), "private/../../outside.txt", "missing.md"]:
        assert "error" in server.read_file(caller="m1", path=bad)


def test_memory_get_and_add(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "DATA", tmp_path)
    assert server.memory(caller="m1", action="get") == {"memories": {}}
    assert server.memory(caller="m1", action="add", key="k", value="v") == {"saved": "k"}
    assert server.memory(caller="m1", action="get") == {"memories": {"k": "v"}}


def test_get_website_rejects_non_http():
    assert "error" in asyncio.run(server.get_website(caller="ceo", url="file:///etc/passwd"))
