# HASHIRU-lite

A minimal multi-agent orchestrator for UCLA CS239 (Fall 2026), based on the design of HASHIRU
([Pai et al., 2025](https://arxiv.org/abs/2506.04255); [code](https://github.com/HASHIRU-AI/HASHIRU)).

- A CEO agent hires managers and workers while it runs. Each runs locally on Ollama or in the cloud through
  LiteLLM.
- Agents talk over **A2A**, and tools are served over **MCP**.
- Every action is traced, so the requirements in [requirements.md](requirements.md) can be checked.

## Run

```bash
cp .env.example .env              # set CEO_MODEL, MODELS and your provider key
uv sync
uv run --env-file .env run.py s1  # scenarios: hello, s1, s2, s3, s4
uv run check.py traces/phase1/*.jsonl
uv run viewer.py                  # trace viewer at http://127.0.0.1:8239
uv run pytest -q
```

Local models need [Ollama](https://ollama.com) running. Any LiteLLM model string works: an `ollama_chat/...`
model is local, and anything else is cloud. A cloud model that LiteLLM can't price is refused at startup;
add its per-token price to `prices.json` (this repo prices NVIDIA NIM's `meta/muse-glimmer-30b` at
Together/Fireworks rates for the same model, as a conservative estimate).

## Files

| File | What it does |
|---|---|
| `server.py` | MCP tools at `/mcp`; one A2A endpoint per agent at `/agents/{name}/` |
| `agent.py` | Agent runtime: LLM loop, MCP calls, A2A `ask_agent`. The single chokepoint that writes the trace |
| `ledger.py` | Agent registry and budget arithmetic |
| `tracelog.py` | JSONL trace and label rules |
| `llm.py` | LiteLLM calls and the wallet cap |
| `policy.py`, `check.py` | R1–R5 as checks over traces |
| `viewer.py`, `viewer.html` | Web page with the architecture, the scenarios and every trace, violations marked in red |
| `run.py` | Scenarios |

## Phases

- **Phase 1** (tag `phase1`): no enforcement. Policies are only prompt text, and the traces in
  `traces/phase1/` show agents breaking them.
- **Phase 2** (later in the course): port to the course's policy-assurance framework, which will enforce
  R1–R5 at the same chokepoint (`agent.call_tool` / `agent.ask_agent`).

## Citation

HASHIRU-lite keeps HASHIRU's core design: a CEO agent that hires and fires agents under cost and memory
limits, favoring local Ollama models over cloud APIs. It leaves out HASHIRU's autonomous tool creation. If
you use this work, please cite the original paper:

```bibtex
@misc{pai2025hashiruhierarchicalagenthybrid,
      title={HASHIRU: Hierarchical Agent System for Hybrid Intelligent Resource Utilization},
      author={Kunal Pai and Parth Shah and Harshil Patel},
      year={2025},
      eprint={2506.04255},
      archivePrefix={arXiv},
      primaryClass={cs.MA},
      url={https://arxiv.org/abs/2506.04255},
}
```
