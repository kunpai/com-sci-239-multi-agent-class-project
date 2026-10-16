import asyncio
from types import SimpleNamespace

import pytest

import llm


def test_is_local():
    assert llm.is_local("ollama_chat/qwen3.5:4b")
    assert llm.is_local("ollama/gemma4:12b")
    assert not llm.is_local("gemini/gemini-2.5-flash")


def test_check_priced_rejects_unknown_cloud_model():
    llm.check_priced(["ollama_chat/anything", "gpt-4.1-mini"])
    with pytest.raises(SystemExit):
        llm.check_priced(["made-up-provider/model-x"])


def test_prices_file_fills_gaps_in_litellms_price_map():
    assert llm.has_price("nvidia_nim/meta/muse-glimmer-30b")   # from prices.json; LiteLLM's map lacks it


def fake_response(text="hi"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))])


def test_chat_returns_message_and_cost(monkeypatch):
    async def fake_acompletion(**kwargs):
        return fake_response("hello")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm.litellm, "completion_cost", lambda completion_response: 0.01)
    monkeypatch.setattr(llm, "spent_total", 0.0)
    msg, cost = asyncio.run(llm.chat("gpt-4.1-mini", [{"role": "user", "content": "x"}]))
    assert msg.content == "hello" and cost == 0.01 and llm.spent_total == 0.01


def test_local_calls_cost_nothing_and_use_ollama(monkeypatch):
    seen = {}

    async def fake_acompletion(**kwargs):
        seen.update(kwargs)
        return fake_response()
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm, "spent_total", 0.0)
    _, cost = asyncio.run(llm.chat("ollama_chat/qwen3.5:4b", []))
    assert cost == 0.0 and seen["api_base"] == llm.OLLAMA_URL and seen["temperature"] == 0


def test_chat_retries_transient_provider_errors(monkeypatch):
    seen = {}

    async def fake_acompletion(**kwargs):
        seen.update(kwargs)
        return fake_response()
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm, "spent_total", 0.0)
    asyncio.run(llm.chat("ollama_chat/qwen3.5:4b", []))
    assert seen["num_retries"] == 2


def test_wallet_cap_stops_all_further_calls(monkeypatch):
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs["model"])
        return fake_response()
    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(llm.litellm, "completion_cost", lambda completion_response: 1.5)
    monkeypatch.setattr(llm, "MAX_USD", 2.0)
    monkeypatch.setattr(llm, "spent_total", 0.0)
    asyncio.run(llm.chat("gpt-4.1-mini", []))      # $1.50 spent
    asyncio.run(llm.chat("gpt-4.1-mini", []))      # $3.00: crosses the cap, but this answer is still returned and traced
    for _ in range(2):                             # every later call, by any agent, is refused before reaching the provider
        with pytest.raises(llm.WalletExceeded):
            asyncio.run(llm.chat("ollama_chat/qwen3.5:4b", []))
    assert len(calls) == 2
