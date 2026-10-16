import agent
import run


def test_scenarios_exist_and_point_at_the_local_page():
    assert set(run.SCENARIOS) == {"hello", "s1", "s2", "s3", "s4"}
    assert f"{agent.BASE}/web/pricing.html" in run.SCENARIOS["s3"]
    assert "ollama_chat/gemma4:12b" in run.SCENARIOS["s1"] and "ollama_chat/gemma4:latest" in run.SCENARIOS["s1"]
    assert "private/notes.md" in run.SCENARIOS["s4"]
