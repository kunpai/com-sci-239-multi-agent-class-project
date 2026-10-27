# HASHIRU-lite

A minimal multi-agent orchestrator for UCLA CS239 (Fall 2026), based on the design of HASHIRU
([Pai et al., 2025](https://arxiv.org/abs/2506.04255); [code](https://github.com/HASHIRU-AI/HASHIRU)).

- A CEO agent hires managers and workers while it runs. Each one runs either locally on Ollama or in the cloud
  through LiteLLM.
- Agents talk over **A2A**, and tools are served over **MCP**.
- Every action is traced, so the requirements in [requirements.md](requirements.md) can be checked.

## Requirements

- **Python 3.13** and **[uv](https://docs.astral.sh/uv/)**. `uv sync` installs everything else from `uv.lock`:
  `mcp`, `a2a-sdk`, `litellm`, `httpx`, `psutil`, `starlette`, `uvicorn` and `pytest`.
- **[Ollama](https://ollama.com)**, needed only for local models. It must be running at `OLLAMA_URL` with the
  local models you list in `MODELS` pulled:
  ```bash
  ollama pull qwen3.5:4b      # used as ollama_chat/qwen3.5:4b
  ollama pull gemma4:12b      # S1 asks for these two
  ollama pull gemma4:latest
  ```
- **An API key for a cloud provider**, needed only for cloud models. Any provider LiteLLM supports works. Set
  the key variable LiteLLM expects for that provider, such as `GEMINI_API_KEY` or `NVIDIA_NIM_API_KEY`.

Tests, `check.py` and the trace viewer need neither Ollama nor a key.

## Configure

```bash
cp .env.example .env
```

| Variable | Meaning | Default |
|---|---|---|
| `CEO_MODEL` | LiteLLM model string for the CEO | required |
| `MODELS` | comma-separated models that `hire_agent` may use. `ollama_chat/...` and `ollama/...` are local; anything else is cloud | `ollama_chat/qwen3.5:4b` |
| `BUDGET_USD` | the CEO's pool: the run's whole budget | `0.50` |
| `MAX_USD` | hard cap on real API spend in one process. Every call after it is crossed is refused | `2.00` |
| `OLLAMA_URL` | Ollama's address | `http://127.0.0.1:11434` |
| `PORT` | port for the MCP and A2A server | `9100` |
| provider key | for example `GEMINI_API_KEY` or `NVIDIA_NIM_API_KEY` | none |

A cloud model that LiteLLM can't price is refused at startup. Add its per-token price to `prices.json` to use
it. This repo prices NVIDIA NIM's `meta/muse-glimmer-30b` at Together/Fireworks rates for the same model, as a
conservative estimate.

**Configurations:**
- **No keys at all:**
  ```bash
  CEO_MODEL=ollama_chat/qwen3.5:4b
  MODELS=ollama_chat/qwen3.5:4b
  ```
- **The traces in `traces/`:** CEO `meta/muse-spark-1.2`, plus
  `MODELS=ollama_chat/qwen3.5:4b,ollama_chat/gemma4:12b,ollama_chat/gemma4:latest,nvidia_nim/meta/muse-glimmer-30b`.
  This setup needs two keys: `META_API_KEY` for the CEO and `NVIDIA_NIM_API_KEY` for the cloud worker.

## Run

```bash
uv sync
uv run --env-file .env run.py hello   # scenarios: hello, s1, s2, s3
uv run --env-file .env run.py chat    # talk to the CEO turn by turn; Ctrl-D, Ctrl-C or /quit to end
uv run --env-file .env chat.py        # the same in a browser at http://127.0.0.1:9100/chat
uv run check.py traces/phase1/*.jsonl # check traces against the policies; exits 1 on any violation
uv run viewer.py                      # trace viewer at http://127.0.0.1:8239
uv run pytest -q                      # 90 tests, no keys or Ollama needed (see tests/README.md)
```

Each run starts one server process with MCP at `/mcp` and one A2A endpoint per agent at `/agents/{name}/`.
It sends the scenario's request to the CEO and writes the trace to `traces/<scenario>-<timestamp>.jsonl`.

### Example

This run uses the no-key configuration and took about 2 minutes on an M-series Mac:

```bash
CEO_MODEL=ollama_chat/qwen3.5:4b MODELS=ollama_chat/qwen3.5:4b uv run run.py hello
```

```text
[ceo -> you] Hello! I haven't said anything else yet in this conversation, but I'm here to help you out. How can I assist you today?
[ceo -> you] done
[ceo -> you]
trace: traces/hello-20261027-102210.jsonl
```

- **The `[ceo -> you]` lines:** the first two are `deliver_to_user` calls, and the last is the CEO's final
  reply, which was empty here.
- **Expected warnings:** the a2a SDK may print `Dispatcher task is not running` warnings; the run is not
  affected.
- **Checking the run:** `uv run check.py traces/hello-*.jsonl` should print `satisfied`. In this trace the CEO
  checked its pool, hired a local worker, asked it, delivered its answer and fired it.

LLM output varies from run to run, even at temperature 0.

## Files

| File | What it does |
|---|---|
| `server.py` | MCP tools at `/mcp`, and one A2A endpoint per agent at `/agents/{name}/` |
| `agent.py` | Agent runtime: the LLM loop, MCP calls and A2A `ask_agent`. It is the single chokepoint that writes the trace |
| `ledger.py` | Agent registry and budget arithmetic |
| `tracelog.py` | JSONL trace and label rules |
| `llm.py` | LiteLLM calls and the wallet cap |
| `policy.py`, `check.py` | R1–R5 (the policies P1–P5) as checks over traces |
| `viewer.py`, `viewer.html` | Web page with the architecture, the scenarios and every trace, violations marked in red. Its Chat tab follows a live chat |
| `chat.py`, `chat.html` | Chat with the CEO in a browser and watch each hire, message and violation as it happens |
| `run.py` | Scenarios, and `chat` for the terminal |
| `data/` | The fictional user's memories (`memory.json`), private notes (`private/notes.md`) and the pricing page with an injected instruction (`web/pricing.html`) |
| `traces/` | Recorded runs: `phase1/` (S1–S3, three each) and `chat/`. See [traces/README.md](traces/README.md) |
| `tests/` | 90 pytest cases. Each case is described in [tests/README.md](tests/README.md) |
| `requirements.md`, `POLICY.md` | The requirements R1–R5 and how the policy is given to agents and checked |
| `submission/hashiru-lite/` | The CS239 application description: `app.md`, `policy.md` (P1–P5), `tools.md`, `agents/` and `episodes/` |
| `package.py` | Checks the description against the code, then builds both submission archives into `dist/` |

## Phase 1

Tag `phase1`. Nothing enforces the requirements: the policies are only prompt text, and the traces in
`traces/phase1/` show agents breaking them.

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
